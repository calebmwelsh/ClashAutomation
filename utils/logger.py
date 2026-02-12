import datetime
import logging
import os

import coloredlogs


class Logger:
    # Default directories for each log level
    LOG_DIRS = {
        'DEBUG': os.path.join('data', 'logging', 'states', 'debug'),
        'INFO': os.path.join('data', 'logging', 'states', 'info'),
        'WARNING': os.path.join('data', 'logging', 'states', 'warning'),
        'ERROR': os.path.join('data', 'logging', 'states', 'error'),
        'CRITICAL': os.path.join('data', 'logging', 'states', 'critical'),
    }

    def __init__(self, name="Clash Workflow", level="INFO"):
        # Ensure all log directories exist
        # for log_dir in self.LOG_DIRS.values():
        #     os.makedirs(log_dir, exist_ok=True)
        self.logger = logging.getLogger(name)
        self.set_level(level)
        self._setup_file_logging()
        self._setup_coloredlogs()

    def _setup_file_logging(self):
        # Create data/logs directory
        log_dir = os.path.join('data', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Timestamped filename
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(log_dir, f"run_{timestamp}.log")
        
        # Create File Handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(self.logger.level)
        
        # Formatter (no color codes)
        formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s  %(message)s")
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)

    def set_level(self, level):
        self.logger.setLevel(level)
        for handler in self.logger.handlers:
            handler.setLevel(level)

    def _setup_coloredlogs(self):
        level_styles = {
            'debug': {'color': 'blue'},
            'info': {'color': 'white'},
            'warning': {'color': 'yellow'},
            'error': {'color': 'red'},
            'critical': {'color': 'red', 'bold': True},
        }
        field_styles = {
            'asctime': {'color': 'white'},
            'name': {'color': 'magenta', 'bold': False},
            'levelname': {'color': 'cyan', 'bold': False},
        }
        coloredlogs.install(
            level=self.logger.level,
            logger=self.logger,
            fmt="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
            level_styles=level_styles,
            field_styles=field_styles
        )

    def get_logger(self):
        return self.logger
