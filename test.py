"""Tests for ftptool."""

import unittest
from StringIO import StringIO

import ftplib
import ftptool

class PhonyDataChannel(object):
    def __init__(self, input_data):
        self.closed = False
        self.input_data = StringIO(input_data)
        for copy_attr in ("read", "readline", "write"):
            setattr(self, copy_attr, getattr(self.input_data, copy_attr))
        self.recv = self.read
        self.send = self.write

    def makefile(self, mode="rb"):
        return self

    def close(self):
        self.closed = True

class PhonyFTPClient(object, ftplib.FTP):
    """A phony FTP client. It puts all sent commands into an instance attribute
    *sent_commands*, and expects to be able to read commands from an instance
    attribute *input_commands*. It is a list, and you can simply append to it
    in the usual way. When that list is exhausted, it should be equivalent of
    the other side disconnecting.

    Create the client object, we could pass connection parameters here.
    >>> c = PhonyFTPClient()

    Stuff in some greeting to be received at connect, then "connect". We should
    get our nice greeting message back.
    >>> c.input_commands.extend(("220-Welcome.", "220 This is a test"))
    >>> c.connect('ftp.google.com', 21)
    '220-Welcome.\\n220 This is a test'

    The phony client tracks where it's "connected"; we gave it these arguments.
    >>> c.connected_to
    ('ftp.google.com', 21)

    Stuff in authentication commands. First ask for a password, then tell the
    client that the login attempt was successful.
    >>> c.input_commands.extend((
    ...     "331 Great, give me a password.",
    ...     "230 OK great, you're logged in now."))

    Then, we log in. This will have ftplib receive the first command, asking it
    for a password, upon which it'll send the command.
    >>> c.login('secret', 'sauce')
    >>> c.login_info
    ('secret', 'sauce', None)
    """

    def __init__(self, host='', user='', passwd='', acct=''):
        # These are commands to simulate receiving of. We pop this list, to get
        # everything in the correct order.
        self.input_commands = []
        # This list contains both sent and received commands. It consists of
        # two-tuples, (d, l) where *d* is the direction in angle brackets, <
        # for receive, > for send. *l* is obviously the line.
        self.dialogue = []
        # When a data channel is to be used, the first index of this list
        # popped and used.
        self.data_channels = []
        # Connection info
        self.connected_to = (None, None)
        self.login_info = (None, None, None)
        # Try to connect if arguments were given, like the real FTP class.
        if host:
            self.connect(host)
            if user:
                self.login(user, passwd, acct)

    def putcmd(self, line):
        self.dialogue.append((">", line))

    def getline(self):
        try:
            line = self.input_commands.pop(0)
        except IndexError:
            raise EOFError("out of input commands")
        self.dialogue.append(("<", line))
        return line

    def ntransfercmd(self, cmd, rest=None):
        # Simulate the real ntransfercmd. We don't need to special-case passive
        # as we use our own data channels in any event.
        if rest is not None:
            self.sendcmd("REST %s" % rest)
        resp = self.sendcmd(cmd)
        if resp[0] == '2':
           resp = self.getresp()
        if resp[0] != '1':
            raise ftplib.error_reply(resp)
        return (self.data_channels.pop(0), None)

    def connect(self, host=None, port=None):
        if host:
            self.connected_to = (host, self.connected_to[1])
        if port:
            self.connected_to = (self.connected_to[0], port)
        # Emulate some of the things that the real connect does. We can't call
        # it though, as it creates sockest n' stuff.
        self.af = 123
        self.welcome = self.getresp()
        return self.welcome

    def login(self, user, passwd=None, acct=None):
        super(PhonyFTPClient, self).login(user, passwd, acct)
        self.login_info = (user, passwd, acct)

    def __str__(self):
        return "<%s connected_to=%r login_info=%r>" % (
            self.__class__.__name__, self.connected_to, self.login_info)

class ClientTest(unittest.TestCase):
    def setUp(self):
        self.client = PhonyFTPClient()
        self.client.input_commands.append("220 Hi.")
        self.host = ftptool.FTPHost.connect("example.org",
            ftp_client=lambda: self.client)

    def test_connected(self):
        self.assertEqual(self.client.welcome,
            "220 Hi.")
        self.assertEqual(self.client.connected_to,
            ("example.org", 21))

    def test_login(self):
        self.client.input_commands.extend((
            "331 Give password.",
            "230-Fine!",
            "230 You're now logged in."))
        self.client.login("fbi", "SecretPassword")
        self.assertEqual(self.client.login_info,
            ("fbi", "SecretPassword", None))

    def test_pwd(self):
        self.client.input_commands.append(
            '257 "/" is your current location.')
        self.assertEqual(self.host.current_directory, "/")

    def test_cwd(self):
        self.client.input_commands.extend((
            '250 OK. Current directory is /test',
            '257 "/test" is your current location.'))
        self.host.current_directory = "/test"
        self.assertEqual(self.host.current_directory, "/test")

    def test_mkdir(self):
        self.client.input_commands.append(
            '257 "testd" : The directory was successfully created')
        self.host.mkdir("testd")

    def test_active_download(self):
        file_contents = "Hello world!"
        # Create a phony data channel and put it on the stack of DCs.
        dc = PhonyDataChannel(file_contents)
        self.client.data_channels.append(dc)
        # We have to run the pwd test first, so ftptool thinks it knows where
        # it is.
        self.test_pwd()
        # These are the expected commands.
        self.client.input_commands.extend((
            "200 TYPE is now 8-bit binary",
            "200 PORT command successful",
            "150 Connecting to data port",
            "226-File successfully transferred",
            "226 Didn't take very long bla bla."))
        # Disable passive mode. The fake commands are for active.
        self.client.set_pasv(False)
        # Then "retrieve" the file.
        self.assertEqual(file_contents,
            self.host.file_proxy("/test.txt").download_to_str())
        self.assertEqual(dc.closed, True)

    def test_pasv_download(self):
        file_contents = "Hello world!"
        # Create a phony data channel and put it on the stack of DCs.
        dc = PhonyDataChannel(file_contents)
        self.client.data_channels.append(dc)
        # We have to run the pwd test first, so ftptool thinks it knows where
        # it is.
        self.test_pwd()
        # These are the expected commands.
        self.client.input_commands.extend((
            "200 TYPE is now 8-bit binary",
            "227 Entering passive mode (1,2,3,4,5,6)",
            "150 Accepted connection",
            "226-File successfully transferred",
            "226 Didn't take very long bla bla."))
        # Enable passive mode.
        self.client.set_pasv(True)
        # Then "retrieve" the file.
        self.assertEqual(file_contents,
            self.host.file_proxy("/test.txt").download_to_str())
        self.assertEqual(dc.closed, True)

    def test_walk(self):
        # Make three data channels, the latter being the
        # subdirectories 'a_dir' and 'x_dir" of the first one.
        self.client.data_channels.extend(
            [PhonyDataChannel(x) for x in
             ("a_dir\nx_dir\ntest\n", "foo\nbar\n", "hello\nworld\n")])
        # Add the proper replies.
        self.client.input_commands.extend((
        "200 Switching to ASCII mode.",
        "150 Here comes the directory listing.",
        "226 Directory send OK.",
        # STAT for a_dir
        "213-Status follows:",
        "drwxr-xr-x   38 1344     1346         4096 May 11 20:48 .",
        "drwxr-xr-x   38 1344     1346         4096 May 11 20:48 ..",
        "-rwxr-xr-x   38 1344     1346         4096 May 11 20:48 foo",
        "-rwxr-xr-x   38 1344     1346         4096 May 11 20:48 bar",
        "213 End of status",
        # STAT for x_dir
        "213-Status follows:",
        "-rwxr-xr-x   38 1344     1346         4096 May 11 20:48 hello",
        "drwxr-xr-x   38 1344     1346         4096 May 11 20:48 .",
        "drwxr-xr-x   38 1344     1346         4096 May 11 20:48 ..",
        "-rwxr-xr-x   38 1344     1346         4096 May 11 20:48 world",

        "213 End of status",
        "213-Status follows:",
        "-rwxr-xr-x   38 1344     1346         4096 May 11 20:48 test",
        "213 End of status",
        # Second NLST call
        "200 Switching to ASCII mode.",
        "150 Here comes the directory listing.",
        "226 Directory send OK.",
        "213-Status follows:",
        "-rwxr-xr-x   38 1344     1346         4096 May 11 20:48 foo",
        "213 End of status",
        "213-Status follows:",
        "-rwxr-xr-x   38 1344     1346         4096 May 11 20:48 bar",
        "213 End of status",
        # Third NLST call
        "200 Switching to ASCII mode.",
        "150 Here comes the directory listing.",
        "226 Directory send OK.",
        "213-Status follows:",
        "-rwxr-xr-x   38 1344     1346         4096 May 11 20:48 hello",
        "213 End of status",
        "213-Status follows:",
        "-rwxr-xr-x   38 1344     1346         4096 May 11 20:48 world",
        "213 End of status"
        ))
        x = []
        for (dirname, sdrs, files) in self.host.walk("/"):
            for sd in sdrs:
                if sd.startswith("x_"):
                    sdrs.remove(sd)
            x.append((dirname, sdrs, files))
        self.assertEqual(x,
            [('/',          ['a_dir'],  ['test']),
             ('/a_dir',     [],         ['foo', 'bar'])])

    def test_makedirs(self):
        self.test_pwd()  # To cache cwd
        self.client.input_commands.extend((
            # These three for the attempt at CWDing. First a failed CWD to
            # dest, then a successful one back to where we were. ftptool also
            # issues a PWD right after a CWD to see where it got to.
            '550 No such directory.',
            '250 OK.',
            '257 "/" is your current location.',
            # First attempt fails, the rest succeed.
            '550 It exists etc.',
            '257 Directory created.',
            '257 Directory created.',
            '257 Directory created.',
            # Now with a relative path.
            '550 No such directory.',
            '250 OK.',
            '257 "/" is your current location.',
            '550 It exists etc.',
            '550 It exists etc.',
            '550 It exists etc.',
            '257 Directory created.'))
        self.host.makedirs("/a_dir/hello/world/foo")
        self.assertEqual([o[1] for o in self.client.dialogue[-14::2]],
            ['CWD /a_dir/hello/world/foo',
             'CWD /',
             'PWD',
             'MKD /a_dir/',
             'MKD /a_dir/hello/',
             'MKD /a_dir/hello/world/',
             'MKD /a_dir/hello/world/foo/'])
        self.host.makedirs("a_dir/hello/world/foo")
        self.assertEqual([o[1] for o in self.client.dialogue[-14::2]],
            ['CWD a_dir/hello/world/foo',
             'CWD /',
             'PWD',
             'MKD a_dir/',
             'MKD a_dir/hello/',
             'MKD a_dir/hello/world/',
             'MKD a_dir/hello/world/foo/'])

if __name__ == "__main__":
    import doctest
    import sys
    res1 = doctest.testmod()
    res2 = unittest.main()
    if res1[0] or not res2.wasSuccessful():
        sys.exit(1)
