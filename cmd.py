#!/usr/bin/env python3
import argparse
import math
import os
import shlex
import sys
from abc import ABCMeta, abstractmethod
from functools import partial


def tuple_leave_unique(tupl):
    # preserves order (>=py3.6 guarantee for dict)
    # (1,2,1,3) -> (1,2,3)
    return tuple(dict.fromkeys(tupl).keys())


def format_listing(files, dirs):
    return tuple(sorted(
        [(f'd {d}', d) for d in dirs] + [(f'f {f}', f) for f in files],
    ))


class StartOverException(Exception):
    pass


class ExitException(Exception):
    pass


class MenuResponse(metaclass=ABCMeta):
    is_fulfilled = False

    @abstractmethod
    def input(self, line):
        pass


class MenuAlert(MenuResponse):
    def __init__(self, message):
        super().__init__()
        self.message = message

    def __str__(self):
        menu_lines = []
        menu_lines.append(self.message)
        menu_lines.append('')
        menu_lines.append('Enter anything to start over. ')
        return '\n'.join(menu_lines)

    def input(self, line):
        self.is_fulfilled = True


class MenuConfirm(MenuResponse):
    def __init__(self, prompt):
        super().__init__()
        self.prompt = prompt
        self.is_confirmed = None
        self.error = None

    def __str__(self):
        menu_lines = []
        menu_lines.append(self.prompt)
        menu_lines.append('')
        if self.error:
            menu_lines.append('Error: %s' % self.error)
        menu_lines.append('y/n? ')
        return '\n'.join(menu_lines)

    def input(self, line):
        if line not in ('y', 'n'):
            self.error = 'Enter either "y" or "n".'
            return
        self.is_confirmed = line == 'y'
        self.is_fulfilled = True


class MenuPrompt(MenuResponse):
    def __init__(self, prompt):
        super().__init__()
        self.prompt = prompt
        self.result = None

    def __str__(self):
        menu_lines = []
        menu_lines.append(self.prompt)
        menu_lines.append('')
        menu_lines.append('> ')
        return '\n'.join(menu_lines)

    def input(self, line):
        self.result = line
        self.is_fulfilled = True


class MenuListing(MenuResponse):
    def __init__(self, title, choices, single_choice=False, chosen=tuple(),
                 page_size=7, with_exit=True, read_only=False):
        super().__init__()
        self.title = [title] if isinstance(title, str) else title
        self.choices = tuple(choices)  # title, value
        self.single_choice = single_choice
        self.chosen = tuple(chosen)
        if self.chosen:
            assert not self.single_choice
        self.page_size = page_size
        self.with_exit = with_exit
        self.read_only = read_only
        self.error = None
        self.page = 0
        self.page_handlers = tuple()
        self.page_items = tuple()
        self._render_page()

    @property
    def page_count(self):
        return int(math.ceil(len(self.choices) / self.page_size))

    def _render_page(self):
        offset = self.page * self.page_size
        choices_slice = self.choices[offset:offset + self.page_size]
        items, handlers = [], []
        for title, value in choices_slice:
            if self.single_choice or self.read_only:
                items.append(title)
            else:
                prefix = '[*]' if value in self.chosen else '[ ]'
                items.append('%s %s' % (prefix, title))
            handlers.append(partial(self._toggle_choice, value))

        if not self.read_only and not self.single_choice:
            items.append('Done')
            handlers.append(self._fulfill)
        if self.page > 0:
            items.append('Previous page')
            handlers.append(partial(self._inc_page, -1))
        if len(self.choices) > offset + self.page_size:
            items.append('Next page')
            handlers.append(partial(self._inc_page, 1))
        if self.with_exit:
            items.append('Cancel and start over')
            handlers.append(self._exit)
        self.page_items = items
        self.page_handlers = handlers

    def _toggle_choice(self, value):
        if self.read_only:
            return
        if value in self.chosen:
            # remove
            self.chosen = tuple_leave_unique(c for c in self.chosen if c != value)
        else:
            # add
            self.chosen = tuple_leave_unique(self.chosen + (value,))
        if self.single_choice:
            self.is_fulfilled = True

    def _inc_page(self, inc):
        self.page += inc

    def _fulfill(self):
        self.is_fulfilled = True

    def _exit(self):
        raise StartOverException()

    def __str__(self):
        menu_lines = []
        for t in self.title:
            menu_lines.append(t)
        menu_lines.append('')
        if len(self.choices) > self.page_size:
            menu_lines.append('Page %s/%s:' % (self.page + 1, self.page_count))
        for idx, title in enumerate(self.page_items):
            menu_lines.append('%s) %s' % (idx + 1, title))
        menu_lines.append('')
        if self.error:
            menu_lines.append('Error: %s' % self.error)
        menu_lines.append('Your choice?  ')
        return '\n'.join(menu_lines)

    def input(self, line):
        try:
            idx = int(line) - 1
            if idx < 0:  # 0 -> page_handlers[-1] -> last item
                raise ValueError()
            handler = self.page_handlers[idx]
        except (ValueError, IndexError):
            self.error = ('Invalid input. Enter a number of the menu item you\'d like '
                          'to choose.')
        else:
            self.error = None
            handler()
            self._render_page()


class MoverState:
    def __init__(self):
        self.marked = set()

    @property
    def cd(self):
        return os.getcwd()

    @cd.setter
    def cd(self, value):
        os.chdir(value)


commands_registry = []


def command_register(cls):
    commands_registry.append(cls)
    return cls


class MenuCommand(metaclass=ABCMeta):
    @classmethod
    def from_menu(cls, mover_state):
        cmd = cls(mover_state)
        return cmd._menu_run()

    @abstractmethod
    def _menu_run(self):
        pass


class CommandlineCommand(metaclass=ABCMeta):
    doc_commandline = ''
    name = None

    @classmethod
    def from_commandline(cls, mover_state, args):
        cmd = cls(mover_state)
        return cmd._commandline_run(cmd._commandline_args_parse(args))

    def _commandline_args_parse(self, args):
        if args:
            raise ValueError("%s doesn't accept any argument" % self.name)
        return args

    @abstractmethod
    def _commandline_run(self, args):
        pass


class Command(metaclass=ABCMeta):

    def __init__(self, mover_state):
        self.mover_state = mover_state


@command_register
class ChangeDirCommand(Command, MenuCommand, CommandlineCommand):
    """Change current directory."""
    doc_commandline = __doc__ + " Accepts single optional arg: directory to list."
    name = 'cd'

    def _commandline_args_parse(self, args):
        if len(args) != 1:
            raise ValueError('cd accepts just one arg: target directory')
        return args

    def _commandline_run(self, args):
        self.change_dir(args[0])
        respond('Changed current directory to: %s' % self.mover_state.cd)

    def _menu_run(self):
        dirs = ListCommand.list_dir(self.mover_state.cd, only_dirs=True, with_parent=True)
        listing = MenuListing('Select a directory to change to', dirs,
                              single_choice=True)
        yield listing
        self.change_dir(listing.chosen[0])

    def change_dir(self, next_cd):
        next_cd = os.path.realpath(os.path.join(self.mover_state.cd, next_cd))
        if not os.path.isdir(next_cd):
            raise ValueError('Not an existing directory: %s' % next_cd)
        self.mover_state.cd = next_cd


@command_register
class ListCommand(Command, MenuCommand, CommandlineCommand):
    """List directory."""
    doc_commandline = __doc__ + " Accepts single optional arg: directory to list."
    name = 'ls'

    def _commandline_args_parse(self, args):
        if not args:
            args = [self.mover_state.cd]
        return args

    def _commandline_run(self, args):
        result = []
        for path in args:
            try:
                output = '\n'.join(title for title, _ in ListCommand.list_dir(path))
            except OSError as e:
                output = str(e)
            result.append(f'Listing directory: {path}\n' + output)
        respond('\n\n'.join(result))

    def _menu_run(self):
        try:
            files_dirs = ListCommand.list_dir(self.mover_state.cd)
        except OSError as e:
            yield MenuAlert(str(e))
            return
        yield MenuListing('Listing %s' % self.mover_state.cd, files_dirs, read_only=True)

    @staticmethod
    def list_dir(path, only_dirs=False, with_parent=False):
        path = os.path.realpath(path)
        for root, dirs, files in os.walk(path):
            if only_dirs:
                files = []
            if with_parent:
                dirs.append('..')
            return format_listing(files, dirs)
        raise OSError('Not an existing dir')


@command_register
class TouchCommand(Command, MenuCommand, CommandlineCommand):
    """Create new empty file."""
    doc_commandline = __doc__ + " Accepts multiple args: paths to files to create."
    name = 'touch'

    def _commandline_args_parse(self, args):
        if not args:
            raise ValueError('touch accepts at least one arg: path to new file')
        return args

    def _commandline_run(self, args):
        for path in args:
            try:
                self._create_file(path)
            except OSError as e:
                respond('Unable to create file: %s: %s' % (path, e))
            else:
                respond('Created an empty file: %s' % path)

    def _menu_run(self):
        prompt = MenuPrompt('Enter file name')
        yield prompt
        if not prompt.result:
            yield MenuAlert('Cannot create a file with empty name')
            return
        path = prompt.result
        try:
            self._create_file(path)
        except OSError as e:
            yield MenuAlert('Unable to create file: %s: %s' % (path, e))
        else:
            yield MenuAlert('Created an empty file: %s' % path)

    def _create_file(self, path):
        path = os.path.realpath(path)
        if os.path.exists(path):
            raise OSError('File already exists')
        with open(path, 'wt'):
            pass


@command_register
class MarkCommand(Command, CommandlineCommand):
    """Mark path to move."""
    doc_commandline = __doc__ + " Accepts multiple args: paths to mark."
    name = 'mark'

    def _commandline_args_parse(self, args):
        if not args:
            raise ValueError('mark accepts at least one arg: path to mark')
        return args

    def _commandline_run(self, args):
        for path in args:
            path = os.path.realpath(path)
            if not os.path.exists(path):
                respond("Unable to mark path: %s: Path doesn't exists" % path)
            else:
                self.mover_state.marked.add(path)
                respond('Marked %s' % path)


@command_register
class UnmarkCommand(Command, CommandlineCommand):
    """Unmark path to move."""
    doc_commandline = __doc__ + " Accepts multiple args: paths to unmark."
    name = 'unmark'

    def _commandline_args_parse(self, args):
        if not args:
            raise ValueError('unmark accepts at least one arg: path to unmark')
        return args

    def _commandline_run(self, args):
        for path in args:
            path = os.path.realpath(path)
            if path not in self.mover_state.marked:
                respond("Unable to unmark path: %s: Path isn't marked" % path)
            else:
                self.mover_state.marked.discard(path)
                respond('Unmarked %s' % path)


@command_register
class ToggleMarkCommand(Command, MenuCommand):
    """Mark/unmark paths to move."""

    def _menu_run(self):
        try:
            files_dirs = ListCommand.list_dir(self.mover_state.cd)
        except OSError as e:
            yield MenuAlert(str(e))
            return
        files_dirs = tuple((title, os.path.realpath(path)) for title, path in files_dirs)
        listing = MenuListing('Mark/unmark paths in %s' % self.mover_state.cd,
                              files_dirs, chosen=self.mover_state.marked)
        yield listing
        self.mover_state.marked = set(listing.chosen)


@command_register
class ShowmarkCommand(Command, CommandlineCommand):
    """Show marked paths."""
    doc_commandline = __doc__ + " Doesn't accept any arg."
    name = 'showmark'

    def _commandline_run(self, args):
        marked = ShowmarkCommand.list_marked(self.mover_state.marked)
        if not marked:
            respond('No paths marked')
        else:
            respond('Marked paths:\n%s' % '\n'.join(marked))

    @staticmethod
    def list_marked(marked):
        files = [path for path in marked if os.path.isfile(path)]
        dirs = [path for path in marked if os.path.isdir(path)]
        if not files and not dirs:
            return None
        return tuple(title for title, _ in format_listing(files=files, dirs=dirs))


@command_register
class MovemarkedCommand(Command, MenuCommand, CommandlineCommand):
    """Move marked paths."""
    doc_commandline = __doc__ + " Doesn't accept any arg."
    name = 'mvmark'

    def _commandline_run(self, args):
        if not self.mover_state.marked:
            respond('Nothing to move: no paths marked')
        for line in self._move():
            respond(line)

    def _menu_run(self):
        if not self.mover_state.marked:
            yield MenuAlert('Nothing to move: no paths marked')
            return
        marked = ShowmarkCommand.list_marked(self.mover_state.marked)
        assert marked
        confirmation = MenuConfirm(
            'Are you sure you want to move the following paths to \'%s\'?\n\n%s' %
            (self.mover_state.cd, '\n'.join('* %s' % p for p in marked)))
        yield confirmation
        if not confirmation.is_confirmed:
            return
        text = '\n'.join(self._move())
        yield MenuAlert(text)

    def _move(self):
        yield 'Moving marked paths to: %s' % self.mover_state.cd
        for path in sorted(set(self.mover_state.marked)):
            try:
                target_name = os.path.basename(path.rstrip('/'))
                target_path = os.path.join(self.mover_state.cd, target_name)
                if os.path.exists(target_path):
                    raise OSError('File exists')
                os.rename(path, target_path)
                self.mover_state.marked.discard(path)
            except OSError as e:
                yield 'Unable to move path: %s: %s' % (path, e)
            else:
                yield 'Moved path: %s' % path


@command_register
class HelpCommand(Command, CommandlineCommand):
    name = 'help'

    def _commandline_run(self, args):
        respond('Known commands:\n%s' % '\n'.join(
            f'{c.name}: {c.doc_commandline}'
            for c in commands_registry
            if issubclass(c, CommandlineCommand) and c.doc_commandline
        ))


@command_register
class ExitCommand(Command, MenuCommand, CommandlineCommand):
    """Exit the program."""
    doc_commandline = __doc__ + " Doesn't accept any arg."
    name = 'exit'

    def _commandline_run(self, args):
        raise ExitException()

    def _menu_run(self):
        confirm = MenuConfirm('Are you sure you want to exit the program?')
        yield confirm
        if confirm.is_confirmed:
            raise ExitException()


class BaseMode(metaclass=ABCMeta):
    name_short = None
    name_verbose = None

    def __init__(self):
        self.mover_state = MoverState()
        self.accepts_input = True

    @abstractmethod
    def print_prompt(self):
        pass

    @abstractmethod
    def process_input(self, line):
        pass

    def close_input(self):
        respond('exiting')
        self.accepts_input = False


class CommandlineMode(BaseMode):
    name_short = 'c'
    name_verbose = 'commandline'

    def __init__(self):
        super().__init__()
        respond('Type "help" to list known commands.')

    def print_prompt(self):
        respond('> ', newline=False)

    def process_input(self, line):
        args = shlex.split(line)
        if not args:
            return

        cmd = args[0]
        args = args[1:]
        command_class = self._get_command_by_name(cmd)
        if command_class:
            try:
                command_class.from_commandline(self.mover_state, args)
            except ValueError as e:
                respond('Command invocation error: %s' % e)
            except ExitException:
                self.close_input()
        else:
            respond('Command not found. List known commands: help')

    def _get_command_by_name(self, name):
        return next((c for c in commands_registry
                     if issubclass(c, CommandlineCommand) and c.name == name), None)


class MenuMode(BaseMode):
    name_short = 'm'
    name_verbose = 'menu'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.create_root_menu()

    def print_prompt(self):
        respond(str(self.current_menu), newline=False, clear_screen=True)

    def process_input(self, line):
        try:
            self.current_menu.input(line)
            if self.current_menu.is_fulfilled:
                self.current_menu = next(self.current_menu_gen, None)
        except StartOverException:
            self.current_menu = None
        except ExitException:
            self.close_input()
        except ValueError as e:
            self.current_menu = MenuAlert('Command invocation error: %s' % e)
            self.current_menu_gen = tuple()
        if self.current_menu is None:
            self.create_root_menu()

    def create_root_menu(self):
        title = ['Current dir: %s' % self.mover_state.cd]
        marked = ShowmarkCommand.list_marked(self.mover_state.marked)
        if marked:
            title.append('Marked paths:')
            title.extend('* %s' % p for p in marked)
        self.current_menu = MenuListing(title,
                                        ((c.__doc__, c) for c in commands_registry
                                         if c.__doc__ and issubclass(c, MenuCommand)),
                                        single_choice=True, with_exit=False)

        def gen(menu):
            command = menu.chosen[0]
            yield from command.from_menu(self.mover_state)
        self.current_menu_gen = gen(self.current_menu)


def respond(t, newline=True, clear_screen=False):
    # https://stackoverflow.com/questions/517970/how-to-clear-the-interpreter-console?noredirect=1&lq=1#comment15050841_517992
    clear_seq = "\x1B[H\x1B[J"

    tmpl = '%s\n' if newline else '%s'
    if clear_screen:
        tmpl = clear_seq + tmpl

    sys.stdout.write(tmpl % t)
    sys.stdout.flush()


def main():
    modes = [CommandlineMode, MenuMode]

    parser = argparse.ArgumentParser(description='A shell to bulk move files.')
    parser.add_argument('mode', type=str, choices=[m.name_short for m in modes],
                        nargs='?', default=CommandlineMode.name_short,
                        help='Mode. %s.' % '. '.join(
                           f'{m.name_short} - {m.name_verbose}' for m in modes))
    args = parser.parse_args()

    m = next((m for m in modes if m.name_short == args.mode),
             CommandlineMode)()
    while m.accepts_input:
        m.print_prompt()
        try:
            line = next(sys.stdin).strip()
        except (StopIteration, KeyboardInterrupt):
            m.close_input()
        else:
            m.process_input(line)


if __name__ == '__main__':
    main()
