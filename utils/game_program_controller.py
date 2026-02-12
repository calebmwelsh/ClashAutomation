import subprocess
import time

import psutil

from utils.settings import logger


class GameProgramController:
    def __init__(self, logger_instance=None):
        self.logger = logger_instance if logger_instance else logger
        
    def start_program(self, program_path):
        try:
            # Start the program
            process = subprocess.Popen(program_path, shell=True)
            self.logger.info(f"Program started: {program_path}")
            time.sleep(10)  # Wait for the program to initialize
            return process
        except FileNotFoundError:
            self.logger.error(f"File not found: {program_path}")
        except Exception as e:
            self.logger.error(f"An error occurred: {e}")

    def stop_program(self, process_name, cmd_directory):
        # Iterate over all running processes
        for proc in psutil.process_iter(['pid', 'name', 'username']):
            try:
                full_cmdline = ' '.join(proc.cmdline()).replace("\\","/")
                # print(proc.info['name'].lower(), full_cmdline)
                # Check if the process name and username match
                if process_name.lower() in proc.info['name'].lower() and full_cmdline == cmd_directory:
                    self.logger.info(f"Found process {proc.info['name']} with PID {proc.info['pid']} running in '{full_cmdline}'")
                    proc.terminate()  # Terminate the process
                    self.logger.info(f"Terminated process {proc.info['name']} with PID {proc.info['pid']}")
                    return  # Exit once the process is terminated
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # Handle exceptions if the process has been terminated already or we don't have permission to interact with it
                pass
        self.logger.warning(f"No process found with name '{process_name}' running in '{cmd_directory}'.")
