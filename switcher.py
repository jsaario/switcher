#! /usr/bin/env python3

# An utility to switch X11 desktops and launching programs.

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
# journal class handles logging to systemd. Use journal.send(string) method to write to the systemd journal.
from systemd import journal


# Functions.

# Returns the window identifier of the launched process.
def get_identifier(pid, desktop, timeout=1.0):
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
		window_ids = get_window_ids(desktop)		
		# Get the window id from the window list.
		window_id = window_ids.get(pid, None)
		if window_id:
			break
		sleep(interval)
	else:
		# No correct window identifier was found before the timeout was reached.
		raise RuntimeError("No window ID found before the timeout was reached.")
	return window_id

# Returns a list of windows for the specified desktop.
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

# Returns a dictionary containing the PIDs and window IDs for the specified desktop.
def get_window_ids(desktop):
	# Create the output.
	window_ids = {}
	# Get the list of windows for this desktop.
	windows = get_windows(desktop)
	# Process the list.
	for window in windows:
		# Get the window id, the desktop and the pid.
		window_id = window.get("id", None)
		window_pid = window.get("pid", None)
		if window_id is None or window_pid is None:
			continue
		# Add the values.
		window_ids.update({window_pid: window_id})
	# All done, return.
	return window_ids

# Switches to the desired desktop and launches the program assigned to the desktop.
def switch_desktop(parameters):
	# Extract values from the given parameters.
	command = parameters.get("command", fallback=None)
	window_class = parameters.get("class", fallback=None)
	desktop = parameters.getint("desktop", fallback=None)
	fullscreen = parameters.getboolean("fullscreen", fallback=False)
	timeout = parameters.getfloat("timeout", fallback=1.0)
	# Check the values.
	if command is None or window_class is None or desktop is None:
		raise ValueError("One of the config keywords 'command', 'class' or 'desktop' is missing.")
	# Split the command string into a list. Warning: This might be a source of bugs!
	command_list = command.split()
	# Swich to the right desktop.
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
		for window in windows:
			run(["wmctrl", "-c", window.get("id", None), "-i"], check="True")
		# Start the program.
		started_program = popen(command_list)
		window_id = get_identifier(pid=started_program.pid, desktop=desktop, timeout=timeout)
	# Make the program fullscreen. "below" flag is also activated to prevent unwanted focus stealing.
	if fullscreen:
		run(["wmctrl", "-r", window_id, "-i", "-b", "add,fullscreen,below"], check="True")
	# All done, return.
	return


# Main.

# Create a parser for the command line arguments.
argument_parser = argumentparser(description="Switches between different virtual desktops and starts designated software on demand.", allow_abbrev=False)
argument_parser.add_argument("-d", "--desktop", type=str, help="Which desktop to switch to.", required=True)
argument_parser.add_argument("--config", type=str, default=expanduser("~")+"/.config/switcher.conf", help="Config file location.")
# Parse the arguments.
arguments = argument_parser.parse_args()

# Create a parser for the config file.
config = configparser()
# Chech that the config file exists and read it.
if isfile(arguments.config):
	config.read(arguments.config)
else:
	argument_parser.print_usage()
	print("error: Config file '%s' not found." %(arguments.config))
	exit(1)

# Check the arguments and the config.
if arguments.desktop not in config.sections():
	print("error: Unsupported desktop given. Supported values are: '%s'." %("', '".join(config.sections())))
	argument_parser.print_usage()
	raise Exception()

# Get the parameters for this instance from the config.
parameters = config[arguments.desktop]

# Try to switch the desktop.
try:
	switch_desktop(parameters)
except:
	# TODO: Figure out how to catch the exception instance and extract the type and the comment (i.e. the last line printed) from it. This line should be logged. When that is finished, the code is ready!!!
	print("What should I do here?")
	raise Exception("I think it failed.")
	#journal.send(msg)

# All done, exit.
exit(0)
