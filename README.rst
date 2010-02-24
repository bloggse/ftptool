=========
 ftptool
=========

Higher-level ftplib

`ftplib` in itself is a bit raw, as it leaves details about the protocol for
the user to handle. `ftptool` abstracts that away, and even provides a neat
interface for file management.

.. note:: ftptool requires Python 2.5 or later.

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
`mirror_to_remote` an empty string or a dot.
