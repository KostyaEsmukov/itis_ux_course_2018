#!/usr/bin/env python3
import sys
import os


def format_listing(files, dirs):
    return '\n'.join(sorted(
            [f'd {d}' for d in dirs] + [f'f {f}' for f in files],
            key=lambda s: s[2:]
    ))


class Traverser:
    def __init__(self):
        self.marked = set()

    @property
    def cd(self):
        return os.getcwd()

    @cd.setter
    def cd(self, value):
        os.chdir(value)

    def cmd_ls(self, args):
        """List directory. Accepts single optional arg: directory to list."""
        if not args:
            args = [self.cd]

        result = []
        for path in args:
            path = os.path.realpath(path)
            root, dirs, files = next(os.walk(path))
            # TODO !!! handle empty dir
            result.append(f'Listing directory: {path}\n' +
                          format_listing(files, dirs))

        respond('\n\n'.join(result))

    def cmd_cd(self, args):
        """Change current directory. Accepts single arg: directory to change to."""
        if len(args) != 1:
            raise ValueError('cd accepts just one arg: target directory')
        next_cd = os.path.realpath(os.path.join(self.cd, args[0]))
        if not os.path.isdir(next_cd):
            raise ValueError('Not an existing directory: %s' % next_cd)
        self.cd = next_cd
        respond('Changed current directory to: %s' % self.cd)

    def cmd_touch(self, args):
        """Create new empty file. Accepts multiple args: paths to files to create."""
        if not args:
            raise ValueError('touch accepts at least one arg: path to new file')
        for path in args:
            path = os.path.realpath(path)
            try:
                if os.path.exists(path):
                    raise OSError('File already exists')
                with open(path, 'wt'):
                    pass
            except OSError as e:
                respond('Unable to create file: %s: %s' % (path, e))
            else:
                respond('Created an empty file: %s' % path)

    def cmd_mark(self, args):
        """Mark path to move. Accepts multiple args: paths to mark."""
        if not args:
            raise ValueError('mark accepts at least one arg: path to mark')
        for path in args:
            path = os.path.realpath(path)
            if not os.path.exists(path):
                respond("Unable to mark path: %s: Path doesn't exists" % path)
            else:
                self.marked.add(path)
                respond('Marked %s' % path)

    def cmd_unmark(self, args):
        """Unmark path to move. Accepts multiple args: paths to unmark."""
        if not args:
            raise ValueError('unmark accepts at least one arg: path to unmark')
        for path in args:
            path = os.path.realpath(path)
            if path not in self.marked:
                respond("Unable to unmark path: %s: Path isn't marked" % path)
            else:
                self.marked.discard(path)
                respond('Unmarked %s' % path)

    def cmd_showmark(self, args):
        """Show marked paths. Doesn't accept any arg."""
        if args:
            raise ValueError("showmark doesn't accept any argument")
        files = [path for path in self.marked if os.path.isfile(path)]
        dirs = [path for path in self.marked if os.path.isdir(path)]
        if not files and not dirs:
            respond('No paths marked')
        else:
            respond('Marked paths:\n%s' % format_listing(files=files, dirs=dirs))

    def cmd_mvmark(self, args):
        """Move marked paths. Doesn't accept any arg."""
        if args:
            raise ValueError("showmark doesn't accept any argument")
        if not self.marked:
            respond('Nothing to move: no paths marked')
            return
        respond('Moving marked paths to: %s' % self.cd)
        for path in sorted(set(self.marked)):
            try:
                target = os.path.basename(path.rstrip('/'))
                os.rename(path, os.path.join(self.cd, target))
                # TODO don't overwrite !!!!!!!!!!!!!
                self.marked.discard(path)
            except OSError as e:
                respond('Unable to move path: %s: %s' % (path, e))
            else:
                respond('Moved path: %s' % path)

    def cmd_help(self, args):
        commands = [cmd for cmd in dir(self)
                    if cmd.startswith('cmd_') and cmd != 'cmd_help']
        respond('Known commands:\n%s' % '\n'.join(
            f'{cmd[4:]}: {getattr(self, cmd).__doc__}' for cmd in commands
        ))


def respond(t):
    sys.stdout.write('%s\n' % t)
    sys.stdout.flush()


def main():
    t = Traverser()
    respond('Type "help" to list known commands.')
    while True:
        sys.stdout.write('> ')
        sys.stdout.flush()
        command = next(sys.stdin).strip()
        if command == 'q':
            respond('exiting')
            break
        else:
            args = command.split(' ')
            cmd = args[0]
            args = args[1:]
            attr_name = 'cmd_%s' % cmd
            if hasattr(t, attr_name):
                try:
                    getattr(t, attr_name)(args)
                except ValueError as e:
                    respond('Command invocation error: %s' % e)
            else:
                respond('Command not found. List known commands: help')


if __name__ == '__main__':
    main()
