#! /usr/bin/env python3

# An utility to switch X11 virtual desktops and launching programs.

# Copyright 2019 Joonas Saario.
# This program is licensed under the GNU GPL version 3 or any later version.


# Imports.

# argumentparser() handles the parsing of command line arguments neatly.
from argparse import ArgumentParser as argumentparser
# expanduser() returns the home directory of the user.
from os.path import expanduser
# configparser() is a neat way for reading and parsing config files.
from configparser import ConfigParser as configparser
# isfile() checks the existence of ordinary files.
from os.path import isfile
# popen() and run() allow to execute external programs within Python and capture their output.
from subprocess import Popen as popen
from subprocess import run
# sleep() allows to halt the process for a specified amount of time.
from time import sleep
# journal class handles logging to systemd. Use journal.send(message) method to write to the systemd journal.
from systemd import journal


# Functions.

# Closes windows on the given list of windows.
def close_windows(windows):
	for window in windows:
		run(["wmctrl", "-c", window.get("id", None), "-i"], check="True")
	# All done, return.
	return None

# Returns the window identifier of the launched process.
# This uses both window PID and class for detecting the correct window.
# PID is the primary reference, class is a handy backup for cases where the PID is either unknown or wrong.
def get_identifier(desktop, window_pid=None, window_class=None, timeout=1.0):
	# Check the input arguments.
	if window_pid is None and window_class is None:
		raise TypeError("Neither window PID nor class given to get_identifier().")
	# Set the polling interval in seconds.
	interval = 0.01
	# Impose hard limits on the timeout.
	if timeout < 0.5:
		timeout = 0.5
	elif timeout > 60.0:
		timeout = 60.0
	# Calculate the timeout_count from the timeout and the interval.
	timeout_count = int(timeout / interval) + 1
	# Poll until the identifier can be found.
	for i in range(timeout_count):
		# Get the dictionary containing all windows on this desktop.
		window_pids, window_classes = get_window_info(desktop)
		# Get the window ID first using the PID. If that fails, use the class.
		window_id = window_pids.get(window_pid, None)
		if not window_id:
			window_id = window_classes.get(window_class, None)
		# If window ID was found, break the loop. Else wait for the next iteration.
		if window_id:
			break
		sleep(interval)
	else:
		# No correct window identifier was found before the timeout was reached.
		raise RuntimeError("No window ID found before the timeout was reached.")
	# All done, return.
	return window_id

# Returns a list of windows for the desktop given as parameter.
def get_windows(desktop):
	# Create the output.
	windows = []
	# Get the list of windows using wmctrl.
	window_listing = run(["wmctrl", "-l", "-x", "-p"], capture_output=True, encoding="utf-8", errors="replace").stdout
	# Split the listing. The result is a list of strings, one item per line.
	window_listing = window_listing.strip().split("\n")
	# Process the listing.
	for line in window_listing:
		splitted_line = line.strip().split()
		# Get the window information.
		try:
			window_id = splitted_line[0]
			window_desktop = int(splitted_line[1])
			window_pid = int(splitted_line[2])
			window_class = splitted_line[3]
			window_hostname = splitted_line[4]
			window_title = " ".join(splitted_line[5:])
		except (IndexError, ValueError):
			continue
		if not window_desktop == desktop:
			continue
		# Append the values.
		windows.append({
			"id": window_id,
			"desktop": window_desktop,
			"pid": window_pid,
			"class": window_class,
			"hostname": window_hostname,
			"title": window_id
			})
	# All done, return.
	return windows

# Returns two dictionaries, one containing the PIDs and other the window classes on the specified desktop.
def get_window_info(desktop):
	# Create the output.
	window_pids = {}
	window_classes = {}
	# Get the list of windows for this desktop.
	windows = get_windows(desktop)
	# Process the list.
	for window in windows:
		# Get the window id, the desktop and the pid.
		window_id = window.get("id", None)
		window_class = window.get("class", None)
		window_pid = window.get("pid", None)
		if window_id is None or window_class is None or window_pid is None:
			continue
		# Add the values.
		window_pids.update({window_pid: window_id})
		window_classes.update({window_class: window_id})
	# All done, return.
	return window_pids, window_classes

# Switches to the desired desktop and launches the program assigned to the desktop.
def switch_desktop(parameters):
	# Extract values from the given parameters.
	command = parameters.get("command", fallback=None)
	window_class = parameters.get("class", fallback=None)
	desktop = parameters.getint("desktop", fallback=None)
	fullscreen = parameters.getboolean("fullscreen", fallback=False)
	activate = parameters.getboolean("activate", fallback=False)
	timeout = parameters.getfloat("timeout", fallback=1.0)
	# Check the values.
	if command is None or window_class is None or desktop is None:
		raise ValueError("One of the config keywords 'command', 'class' or 'desktop' is missing.")
	# Split the command string into a list. Warning: This might be a source of bugs!
	command_list = command.split()
	# Switch to the correct desktop.
	run(["wmctrl", "-s", str(desktop)], check="True")
	# Check if the program is already running.
	windows = get_windows(desktop)
	for window in windows:
		# This will pick the first matching window! In this use case it does not matter.
		if window.get("class", None) == window_class:
			is_running = True
			window_id = window.get("id", None)
			break
	else:
		is_running = False
	# If the program is not running, i.e. a window of the correct class is not found, close all other windows and start the program.
	if not is_running:
		# Close all other windows.
		close_windows(windows)
		# Start the program.
		started_program = popen(command_list)
		window_id = get_identifier(desktop, window_pid=started_program.pid, window_class=window_class, timeout=timeout)
		# Make the program fullscreen.
		if fullscreen:
			run(["wmctrl", "-r", window_id, "-i", "-b", "add,fullscreen"], check="True")
	# Activate the window.
	if activate:
		run(["wmctrl", "-a", window_id, "-i"], check="True")
	# All done, return.
	return None

# Communication and error handling routine. Prints and logs messages and exits if necessary.
def communicate(message, print_message=True, log_message=True, quit=True, exit_code=1):
	if print_message:
		print(message)
	if log_message:
		journal.send("[switcher.py] " + message)
	if quit:
		exit(exit_code)
	# All done, return.
	return None


# Main.

# Create a parser for the command line arguments.
argument_parser = argumentparser(description="Switches between X11 virtual desktops and starts designated software on demand.", allow_abbrev=False)
argument_parser.add_argument("-d", "--desktop", type=str, help="Switch to desktop DESKTOP, as defined in the config.", required=True)
argument_parser.add_argument("--config", type=str, default=expanduser("~")+"/.config/switcher.conf", help="Set the config file location.")
# Parse the arguments.
arguments = argument_parser.parse_args()

# Create a parser for the config file.
config = configparser()
# Chech that the config file exists and read it.
if isfile(arguments.config):
	config.read(arguments.config)
else:
	argument_parser.print_usage()
	communicate("error: Config file '%s' not found." %(arguments.config), quit=True)

# Check the arguments and the config.
if arguments.desktop not in config.sections():
	argument_parser.print_usage()
	communicate("error: Unsupported desktop given. Supported values are: '%s'." %("', '".join(config.sections())), quit=True)

# Get the parameters for this instance from the config.
parameters = config[arguments.desktop]

# Try to switch the desktop.
try:
	switch_desktop(parameters)
except Exception as exception:
	# Get the values for the logged error message.
	exception_type = type(exception).__name__
	exception_message = str(exception)
	# Log the message and exit with a non-zero exit code to denote an error.
	communicate("%s: %s" %(exception_type, exception_message), quit=True)

# All done, exit.
exit(0)
