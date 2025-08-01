#!./.venv/bin/python3

import datetime
import os
import pty
import re
import select
import subprocess
import time

from io import StringIO
from rich.console import Console
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, ScrollableContainer, Grid
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListView,
    ListItem,
    OptionList,
    RichLog,
)
from textual.worker import get_current_worker

RUBY_RED = "#D01D37"
GREY = "#242526"
DARK_GREY = "#1B1B1D"
LIGHT_GREY = "#EFEFEF"
ANTRACITE = "#2F303B"
WHITE = "#FFFFFF"

husarion_dark_theme = Theme(
    name="husarion-dark",
    primary=RUBY_RED,
    foreground=WHITE,
    background=DARK_GREY,
    surface=GREY,
    dark=True,
)

husarion_light_theme = Theme(
    name="husarion-light",
    primary=RUBY_RED,
    foreground=ANTRACITE,
    background=WHITE,
    surface=LIGHT_GREY,
    dark=False,
)


class CommandHandler(RichLog):
    log_text = reactive("")

    def on_mount(self):
        self.auto_scroll = True

    def watch_log_text(self, value: str) -> None:
        text = Text.from_ansi(value)

        # from_ansi method, for some reason sometimes adds double '\n' at the end.
        # This is a workaround to make logs appear nicely formatted,
        # but may in some cases where double '\n' were intended produce incorrect output.
        # This is a price I'm willing to pay.
        lines = text.split("\n\n")
        for line in lines:
            self.write(line)

    @work(exclusive=True, thread=True)
    def run_command(self, command: str) -> None:
        """
        Run command in separate thread and log the output in realtime.
        """

        self.log_text = "---"

        timeout = 0.1
        master_fd, slave_fd = pty.openpty()

        cmd = command.split(" ")
        process = subprocess.Popen(
            cmd,
            stdout=slave_fd,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )

        while not get_current_worker().is_cancelled:
            ready, _, _ = select.select([master_fd], [], [], timeout)
            if ready:
                data = os.read(master_fd, 1024)
                if not data:
                    continue
                self.log_text = data.decode("utf-8").strip()

            if process.poll() is not None:
                break

        process.kill()

    async def run_command_wait(self, command) -> str:
        """
        Run command and wait fot the output. Return the output.
        """

        output = subprocess.run(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        return output.stdout

    def cancel(self):
        self.workers.cancel_all()


class ConfirmationScreen(ModalScreen[bool]):
    def __init__(self, question: str) -> None:
        self._question = question
        super().__init__()

    def compose(self) -> ComposeResult:
        with Grid(id="grid"):
            yield Label(self._question, id="question")
            yield OptionList("Yes", "No", id="options")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.prompt == "Yes":
            self.dismiss(True)
        else:
            self.dismiss(False)


class SelectionScreen(ModalScreen[str]):
    BINDINGS = [
        ("escape", "app.pop_screen", "Return to the previous screen"),
    ]

    def __init__(self, list_title, options: list[str]) -> None:
        super().__init__()
        self._list_title = list_title
        self._options = options

    def compose(self) -> ComposeResult:
        with Grid(id="grid"):
            yield Label(self._list_title, id="title")
            yield OptionList()

    def on_mount(self) -> None:
        option_list = self.query_one(OptionList)
        for option in self._options:
            option_list.add_option(option)

        option_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.prompt)


class CustomButton(Button):
    def on_focus(self) -> None:
        self.variant = "primary"

    def on_blur(self) -> None:
        self.variant = "default"


class DriverLogsScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._last_log_time = None

    def compose(self) -> ComposeResult:
        yield Footer(id="footer")
        with Container(id="tools"):
            yield CustomButton("Refresh", id="refresh", variant="primary")
            yield CustomButton("Save to file", id="save")
        yield CommandHandler(id="driver_logs", wrap=True)

    def on_screen_resume(self) -> None:
        self._run_logs_command()

    def on_screen_suspend(self) -> None:
        self._last_log_time = time.time()
        self.query_one(CommandHandler).cancel()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh":
            self.query_one(CommandHandler).clear()
            self._last_log_time = None
            self._run_logs_command()
        elif event.button.id == "save":
            self._save_logs()

    def _run_logs_command(self) -> None:
        command = "just driver_logs -f -n 10000"
        if self._last_log_time:
            time_ms = int((time.time() - self._last_log_time) * 1000)
            command += f" --since {time_ms}ms"

        self.query_one(CommandHandler).run_command(command)

    def _save_logs(self) -> None:
        strips = self.query_one(CommandHandler).lines
        text = Text()
        for strip in strips:
            for segment in strip:
                text.append(segment.text, segment.style)
            text.append("\n")

        ansi_text = self._text_to_ansi(text)

        date = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        with open(f"driver-logs-{date}.txt", "w") as file:
            file.write(ansi_text)

    def _text_to_ansi(self, strip_obj) -> str:
        buffer = StringIO()
        console = Console(file=buffer, force_terminal=True, color_system="truecolor")
        console.print(strip_obj, end="")
        return buffer.getvalue()


class Configurator(App):
    """A Textual app to manage Husarion UGV robot."""

    BINDINGS = [
        ("q", "quit", "Quit the app"),
        ("d", "toggle_dark", "Toggle dark mode"),
    ]
    CSS_PATH = os.path.join(os.path.dirname(__file__), "style.tcss")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(id="header")
        yield Footer(id="footer")

        with Container(id="top"):
            with ScrollableContainer(id="command_list"):
                yield ListView(
                    ListItem(Label("Update Configuration"), id="update_config"),
                    ListItem(Label("Restart Driver"), id="restart_driver"),
                    ListItem(
                        Label("Show Robot Info", id="show_robot_info_text"),
                        id="show_robot_info",
                    ),
                    ListItem(Label("Driver Logs"), id="driver_logs"),
                    ListItem(Label("Restore Default Configuration"), id="restore_default"),
                    ListItem(Label("List Driver Versions"), id="list_driver_versions"),
                    ListItem(Label("Update Driver Version"), id="update_driver_version"),
                )
            yield Label(id="robot_info", classes="hidden")

        yield CommandHandler(id="output_log")

    async def on_mount(self) -> None:
        self.register_theme(husarion_dark_theme)
        self.register_theme(husarion_light_theme)
        self.theme = "husarion-dark"
        self.title = "Husarion UGV Configurator"
        self.query_one(ListView).focus()
        self.install_screen(DriverLogsScreen(), "driver_logs_screen")
        await self._update_robot_info()

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.theme = "husarion-light" if self.theme == "husarion-dark" else "husarion-dark"

    @work
    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        id = event.item.id
        command_loger = self.query_one(CommandHandler)
        if id == "update_config":
            command_loger.run_command("just update_config")
        elif id == "restart_driver":
            command_loger.run_command("just restart_driver")
        elif id == "show_robot_info":
            robot_info = self.query_one("#robot_info")
            robot_info_text = self.query_one("#show_robot_info_text")
            if robot_info.has_class("hidden"):
                robot_info.remove_class("hidden")
                robot_info_text.update("Hide Robot Info")
            else:
                robot_info.add_class("hidden")
                robot_info_text.update("Show Robot Info")
        elif id == "driver_logs":
            self.push_screen("driver_logs_screen")
        elif id == "restore_default":
            await self._restore_default()
        elif id == "list_driver_versions":
            ros_distro = await self.push_screen_wait(
                SelectionScreen("Choose ROS Distro", ["humble", "jazzy"])
            )
            command_loger.run_command(f"just list_driver_versions {ros_distro}")
        elif id == "update_driver_version":
            await self._update_driver_version()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        event.item.scroll_visible()

    async def _update_robot_info(self) -> None:
        output = await self.query_one(CommandHandler).run_command_wait("just robot_info")
        robot_model = re.search(r"ROBOT_MODEL_NAME=(.+)", output)
        robot_version = re.search(r"ROBOT_VERSION=(.+)", output)
        robot_serial_no = re.search(r"ROBOT_SERIAL_NO=(.+)", output)
        system_version = re.search(r"SYSTEM_BUILD_VERSION=(.+)", output)
        driver_version = re.search(r"DRIVER_VERSION=.*:([^:\n]+)", output)

        robot_model = robot_model.group(1) if robot_model else "----"
        robot_version = robot_version.group(1) if robot_version else "----"
        robot_serial_no = robot_serial_no.group(1) if robot_serial_no else "----"
        system_version = system_version.group(1) if system_version else "----"
        driver_version = driver_version.group(1) if driver_version else "----"

        robot_info_str = Text()
        robot_info_str.append("Robot Information\n", style="bold")
        robot_info_str.append("-----------------\n")
        robot_info_str.append("Model: ", style="bold")
        robot_info_str.append(f"{robot_model.capitalize()}\n")
        robot_info_str.append("Version: ", style="bold")
        robot_info_str.append(f"{robot_version}\n")
        robot_info_str.append("Serial No: ", style="bold")
        robot_info_str.append(f"{robot_serial_no}")
        robot_info_str.append("\nSystem Version: ", style="bold")
        robot_info_str.append(f"{system_version}\n")
        robot_info_str.append("Driver Version: ", style="bold")
        robot_info_str.append(f"{driver_version}\n")
        robot_info = self.query_one("#robot_info")
        robot_info.update(robot_info_str)

    async def _restore_default(self) -> None:
        option = await self.push_screen_wait(
            SelectionScreen("Choose restore mode", ["soft", "hard"])
        )

        confirmation_msg = (
            "This operation may override changes made in the 'config' directory.\n"
            "Are you sure you want to continue?"
        )
        command = "just restore_default " + option
        if option == "hard":
            confirmation_msg = (
                "Restoring configuration in 'hard' mode will completely erase all files from the "
                "'config' directory except for ones in 'common' subdirectory.\n"
                "Are you sure you want to continue?"
            )

        if await self.push_screen_wait(ConfirmationScreen(confirmation_msg)):
            self.query_one(CommandHandler).run_command(command)

    async def _update_driver_version(self) -> None:
        ros_distro = await self.push_screen_wait(
            SelectionScreen("Choose ROS Distro", ["humble", "jazzy"])
        )

        output = await self.query_one(CommandHandler).run_command_wait(
            f"just list_driver_versions {ros_distro}"
        )

        versions = output.split("\n")
        # filter out the versions, and invert list order
        versions = [
            version for version in versions[::-1] if re.search(r"\d+\.\d+\.\d+-\d{8}", version)
        ]
        version = await self.push_screen_wait(SelectionScreen("Choose version", versions))

        if version:
            self.query_one(CommandHandler).run_command(f"just update_driver_version {version}")


if __name__ == "__main__":
    app = Configurator()
    app.run()
