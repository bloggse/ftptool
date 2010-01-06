"""Higher-level ftplib

`ftplib` in itself is a bit raw, as it leaves details about the protocol for
the user to handle. `ftptool` abstracts that away, and even provides a neat
interface for file management.

Connecting & Authenticating
===========================

Code says more than words, so let's look at an example: connecting.

>>> a_host = FTPHost.connect("ftp.python.org", user="foo", password="bar")

`connect` is a classmethod that lets you create an `FTPHost` instance with an
underlying `ftplib.FTP` instance. 

Working with Directories
========================

Changing Working Directory
--------------------------

Changing and getting the current directory is implemented as a property called
`current_directory`. It is lazy; it won't ask the server which the current
directory is until you ask for it.

Note that since it's a property, this will actually go one level up:

>>> a_host.current_directory = ".."

Similarly, this will descend into the "foo" directory:

>>> a_host.current_directory = "foo"

In most cases, it's easier to just specify absolute paths:

>>> a_host.current_directory = "/foo"

`current_directory` will always be the server-side representation; when you
change directory, it ends up sending a ``CWD`` and then a ``PWD`` to get the
result of the operation (since the FTP protocol doesn't define what the reply
text to a ``CWD`` is.)

Listing and Walking the Directory Tree
--------------------------------------

A `os.walk` interface is implemented for walking the directory tree:

>>> for (dirname, subdirs, files) in a_host.walk("/a_dir"):
...     print dirname, "has file(s)", ", ".join(files)
...
/a_dir has file(s) foo, bar
/a_dir/other_dir has file(s) hello
/a_dir/some_dir has file(s)

Just like `os.walk`, you can remove entries in the `subdirs` list to avoid
descending into them:

>>> for (dirname, subdirs, files) in a_host.walk("/a_dir"):
...     for subdir in subdirs:
...         if subdir.startswith("other_"):
...             subdirs.remove(subdir)
...     print dirname, "has file(s)", ", ".join(files)
...
/a_dir has file(s) foo, bar
/a_dir/some_dir has file(s)

You can non-recursively list a directory using `listdir`:

>>> a_host.listdir("/a_dir")
(['other_dir', 'some_dir'], ['foo', 'bar'])

Creating, Deleting and Renaming
-------------------------------

The most simple form of creating a directory is `mkdir`. You simply give it a
directory to create, and so it does:

>>> a_host.mkdir("/new_dir")

If you just want to ascertain that a directory is ready, i.e., exists for an
upload, you could use `makedirs` which tries to create every part of the
directory, piece by piece.

>>> a_host.makedirs("/a_dir/some_dir/a_new_dir/other_new_dir")

Would, hypothetically, create ``a_new_dir`` and ``other_new_dir``.

`ftptool` implements it by first trying to change directory into the given
path, to see if it exists, and then changes back. If it does, it simply
returns, otherwise it creates the directories piece by piece.

Using the File Proxy
====================

Files in `ftptool` are implemented using proxy objects called `FTPFileProxy`.
They represent a file on a remote host. Using them is easy as pie!

>>> a_host.file_proxy("/a_dir/foo").download_to_str()
'This is the file "foo".'
>>> a_host.file_proxy("/a_dir/new_file").upload_from_str("Hello world!")

The Three Upload & Download Methods
-----------------------------------

`ftptool` provides three ways of uploading or downloading files:
* to/from_str: using a str object,
* to/from_file: using a filename,
* and the default: using a file-like object.

Given:
>>> f = a_host.file_proxy("/foo.txt")

You could upload and download from str using these two:
>>> f.upload_from_str("Hi!")
>>> f.download_to_str()
'Hi!'

And using a filename like this:
>>> f.upload_from_file("/etc/motd")
>>> f.download_to_file("/tmp/motd")

And lastly, using file-like objects:
>>> f.upload(StringIO("Test!"))
>>> fp = StringIO()
>>> f.download(fp)
>>> fp.getvalue()
'Test!'

Renaming Files
--------------

Renaming is a method of the file proxies, called `rename`. It returns a new
file proxy for the renamed-to file, so the common pattern will be:

>>> a_file = a_host.file_proxy("hello_world")
>>> a_file = a_file.rename("foobar")

This will issue a rename command, too, so `a_file` will essentially be the same
as before, with a new name and a new instance ID.

Deleting Files
--------------

Deleting a file is much like renaming it: it's a method of the file proxies,
called `delete`. It, however, doesn't have a meaningful return value.

>>> a_file.delete()

Mirroring
=========

`ftptool` supports two types of mirroring: local to remote, and remote to
local. As in, it can download a whole directory and all descendants into a
local directory, for you to play with. It can also upload a whole directory to
a remote host.

The first one, downloading, is called `mirror_to_local`. It's used like so:

>>> a_host.mirror_to_local('/a_dir', 'my_copy_of_a_dir')

The cousin, mirror_to_remote, has the same signature; source first, then
destination.

>>> a_host.mirror_to_remote('my_copy_of_a_dir', '/a_dir')

If the local working directory is the one you want to upload, you can just give
`mirror_to_remote` an empty string or a dot:
"""

__docformat__ = "reStructuredText"

import os
from os import path
try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO
import posixpath
import socket
import ftplib

socket._no_timeoutsocket = socket.socket
timeoutsocket = None
try:
    import timeoutsocket
except ImportError, e:
    from warnings import warn
    warn("%s - socket timeouts disabled" % (e,))

class FTPHost(object):
    """Represent a connection to a remote host.

    A remote host has a working directory, and an ftplib object connected.
    """

    def __init__(self, ftp_obj):
        """Initialize with a ftplib.FTP instance (or an instance of a
        subclass). Use the classmethod connect to create an actual ftplib
        connection and get an FTPHost instance.
        """
        self.ftp_obj = ftp_obj

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.ftp_obj)

    def __str__(self):
        return "<%s at %s:%d (%s)>" % (self.__class__.__name__,
            self.ftp_obj.host, self.ftp_obj.port, self.ftp_obj)

    @classmethod
    def connect(cls, host, port=21, user=None, password=None, account=None,
            ftp_client=ftplib.FTP, debuglevel=0, timeout=None):
        """Connect to host, using port. If user is given, login with given
        user, password and account. The two latter can be None, in which case
        ftplib will set the password to 'anonymous@'. You can choose which
        class to instance by means of ftp_client.
        """
        ftp_obj = ftp_client()
        ftp_obj.set_debuglevel(debuglevel)
        # Hack alert: Make socket.socket be the timeoutsocket instead of the
        # real socket.socket when a timeout is specified.
        if timeout and not timeoutsocket:
            raise ImportError("previously failed to import timeoutsocket")
        elif timeout and timeoutsocket:
            timeoutsocket.setDefaultSocketTimeout(timeout)
            socket.socket = timeoutsocket.timeoutsocket
        ftp_obj.connect(host, port)
        # Then restore the real socket.socket and timeout.
        socket.socket = socket._no_timeoutsocket
        if timeoutsocket:
            timeoutsocket.setDefaultSocketTimeout(None)
        # And log in.
        if user:
            ftp_obj.login(user, password, account)
        return cls(ftp_obj)

    def file_proxy(self, filename):
        """Creates a file proxy object for filename. See FTPFileProxy."""
        return FTPFileProxy(self.ftp_obj,
            posixpath.join(self.current_directory, filename))

    def get_current_directory(self):
        if not hasattr(self, "_cwd"):
            self._cwd = self.ftp_obj.pwd()
        return self._cwd

    def set_current_directory(self, directory):
        self.ftp_obj.cwd(directory)
        self._cwd = self.ftp_obj.pwd()

    current_directory = property(get_current_directory, set_current_directory)

    def mkdir(self, directory):
        """Make directory."""
        self.ftp_obj.mkd(directory)

    def walk(self, directory):
        """Emulates os.walk very well, even the caveats."""
        (subdirs, files) = self.listdir(directory)
        # Yield value.
        yield (directory, subdirs, files)
        # Recurse subdirs.
        for subdir in subdirs:
            for x in self.walk(posixpath.join(directory, subdir)):
                yield x

    def listdir(self, directory):
        """Returns a list of files and directories at `directory`, relative to
        the current working directory. The return value is a two-tuple of
        (dirs, files).
        """
        # Get files and directories.
        flist = []
        self.ftp_obj.dir(directory, flist.append)
        flist = [x.split() for x in flist]
        # Sort to lists.
        subdirs = [x[-1] for x in flist if x[0].startswith('d')]
        files = [x[-1] for x in flist if x[0].startswith('-')]
        return (subdirs, files)

    def mirror_to_local(self, source, destination):
        """Download remote directory found by source to destination."""
        # Cut off excess slashes.
        source = source.rstrip("/")
        destination = destination.rstrip("/")

        for current_dir, subdirs, files in self.walk(source):
            # current_destination will be the destination directory, plus the
            # current subdirectory. Have to treat the empty string separately,
            # because otherwise we'd be skipping a byte of current_dir,
            # because of the +1, which is there to remove a slash.
            if source:
                current_destination = path.join(destination,
                    current_dir[len(source) + 1:])
            else:
                current_destination = path.join(destination, current_dir)
            # Create all subdirectories lest they exist.
            for subdir in subdirs:
                subdir_full = path.join(current_destination, subdir)
                if not path.exists(subdir_full):
                    os.mkdir(subdir_full)
            # Download all files in current directory.
            for filename in files:
                target_file = path.join(current_destination, filename)
                remote_file = posixpath.join(source, current_dir, filename)
                self.file_proxy(remote_file).download_to_file(target_file)

    def mirror_to_remote(self, source, destination, create_destination=False,
            ignore_dotfiles=True):
        """Upload local directory `source` to remote destination `destination`.

        Create destination directory only if `create_destination` is True, and
        don't upload or descend into files or directories starting with a dot
        if `ignore_dotfiles` is True.
        """
        # Cut off excess slashes.
        source = source.rstrip("/")
        destination = destination.rstrip("/")

        if ignore_dotfiles and \
                any(part.startswith(".") for part in destination.split("/")):
            raise ValueError("cannot have a destination with dots when "
                "ignore_dotfiles is True")

        # Create remote FTP destination
        if create_destination:
            try:
                self.makedirs(destination)
            except ftplib.Error:
                pass

        for current_dir, subdirs, files in os.walk(source):
            # Current remote destination = destination dir + current.
            # See mirror_to_local for the census of special-casing the empty
            # string.
            if source:
                remote_dest_dir = posixpath.join(destination,
                    current_dir[len(source) + 1:])
            else:
                remote_dest_dir = posixpath.join(destination, current_dir)

            # Clean subdirs & files from dotfiles if wanted - some FTP daemons
            # hate dotfiles.
            if ignore_dotfiles:
                # Copy the list, and remove dotfiles and dirs from the real
                # list. We need to use remove and not some shady filter
                # because otherwise we'll walk into dotdirs and defeat the
                # purpose of the parameter.
                for subdir in subdirs[:]:
                    if subdir.startswith("."):
                        subdirs.remove(subdir)
                for filename in files[:]:
                    if filename.startswith("."):
                        files.remove(filename)

            # Create all directories required.
            for subdir in subdirs:
                # Ignore FTP exceptions here because if they're fatal, we'll
                # get it later when we upload.
                try:
                    self.mkdir(posixpath.join(remote_dest_dir, subdir))
                except ftplib.Error, e:
                    pass

            # Upload all files.
            for filename in files:
                local_source_file = path.join(current_dir, filename)
                remote_dest_file = posixpath.join(remote_dest_dir, filename)
                f = self.file_proxy(remote_dest_file)
                f.upload_from_file(local_source_file)

    def makedirs(self, dpath):
        """Try to create directories out of each part of `dpath`.

        First tries to change directory into `dpath`, to see if it exists. If
        it does, returns immediately. Otherwise, splits `dpath` up into parts,
        trying to create each accumulated part as a directory.
        """
        # First try to chdir to the target directory, to skip excess attempts
        # at directory creation. XXX: Probably should try full path, then cut
        # off a piece and try again, recursively.
        pwd = self.current_directory
        try:
            self.current_directory = dpath
        except ftplib.Error:
            pass
        else:
            return
        finally:
            self.current_directory = pwd
        # Then if we're still alive, split the path up.
        parts = dpath.split(posixpath.sep)
        # Then iterate through the parts.
        cdir = ""
        for dir in parts:
            cdir += dir + "/"
            # No point in trying to create the directory again when we only
            # added a slash.
            if not dir:
                continue
            try:
                self.mkdir(cdir)
            except ftplib.Error, e:
                pass

    def quit(self):
        """Send quit command and close connection."""
        self.ftp_obj.quit()

    def close(self):
        """Close connection ungracefully."""
        self.ftp_obj.close()

    def try_quit(self):
        """Attempt a quit, always close."""
        try:
            self.quit()
        except:
            self.close()

class FTPFileClient(FTPHost):
    """Class for emulating an FTP client, that is, get & put files to and from.
    """

    def _apply_all(self, filenames, f):
        rs = []
        for filename in filenames:
            source, destination = filename, path.basename(filename)
            rs.append(f(source, destination))
        return rs

    def get(self, source, destination):
        return self.file_proxy(source).download_to_file(destination)

    def put(self, source, destination):
        return self.file_proxy(destination).upload_from_file(source)

    def delete(self, filename):
        return self.file_proxy(filename).delete()

    # {{{ m*
    def mget(self, filenames):
        return self._apply_all(self.get, filenames)

    def mput(self, filenames):
        return self._apply_all(self.put, filenames)

    def mdelete(self, filenames):
        return self._apply_all(self.delete, filenames)
    # }}}


class ExtensionMappedFTPHost(FTPHost):
    """Takes a mapping of extensions to rewrite to another extension.  An
    extension is defined as "the bytes after the last dot". The mapping should
    have keys _without_ a dot, and so should the value. The value can be set to
    the empty string, and the end result will _not_ have a trailing dot.
    """

    @classmethod
    def connect(cls, *a, **kw):
        extension_map = kw.pop("extension_map", {})
        self = super(ExtensionMappedFTPHost, cls).connect(*a, **kw)
        self.extension_map = extension_map
        return self

    def file_proxy(self, filename):
        for key in self.extension_map:
            if filename.endswith("." + key):
                # Remove old extension.
                filename = filename[:-len(key) - 1]
                # Add the new.
                new_extension = self.extension_map[key]
                if new_extension:
                    filename += "." + new_extension
                break
        return super(ExtensionMappedFTPHost, self).file_proxy(filename)

class FTPFileProxy(object):
    def __init__(self, ftp_obj, filename):
        """Initialize file an ftplib.FTPConnection, and filename."""
        self.ftp_obj = ftp_obj
        self.filename = filename

    def upload(self, fp):
        """Uploadad file from file-like object fp."""
        self.ftp_obj.storbinary("STOR %s" % (self.filename,), fp)

    def upload_from_str(self, v):
        """Upload file from contents in string v."""
        self.upload(StringIO(v))

    def upload_from_file(self, filename):
        """Upload file from file identified by name filename."""
        fp = file(filename, "rb")
        try:
            self.upload(fp)
        finally:
            fp.close()

    def download(self, fp):
        """Download file into file-like object fp."""
        self.ftp_obj.retrbinary("RETR %s" % (self.filename,), fp.write)

    def download_to_str(self):
        """Download file and return its contents."""
        fp = StringIO()
        self.download(fp)
        return fp.getvalue()

    def download_to_file(self, filename):
        """Download file into file identified by name filename."""
        fp = file(filename, "wb")
        try:
            self.download(fp)
        finally:
            fp.close()

    def delete(self):
        """Delete file."""
        self.ftp_obj.delete(self.filename)

    def rename(self, new_name):
        """Rename file to new_name, and return an instance of that file."""
        new_abs_name = posixpath.join(path.dirname(self.filename), new_name)
        self.ftp_obj.rename(self.filename, new_abs_name)
        return self.__class__(self.ftp_obj, new_abs_name)
