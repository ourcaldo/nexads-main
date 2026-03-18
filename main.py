"""
main.py — nexAds entry point.

Usage:
  python main.py           # run automation
  python main.py --config  # open configuration GUI
"""

import sys
import atexit
import signal
import multiprocessing
from argparse import ArgumentParser


_AUTOMATION_INSTANCE = None


def _shutdown_handler(signum=None, frame=None):
    """Handle process termination signals and stop workers cleanly."""
    global _AUTOMATION_INSTANCE
    if _AUTOMATION_INSTANCE is not None:
        try:
            _AUTOMATION_INSTANCE.stop()
        except Exception as e:
            print(f"Shutdown cleanup error: {e}")


def main():
    global _AUTOMATION_INSTANCE

    parser = ArgumentParser(description='nexAds Automation Tool')
    parser.add_argument('--config', action='store_true', help='Open configuration GUI')
    args = parser.parse_args()

    if args.config:
        from PyQt5.QtWidgets import QApplication
        from app.ui.config_window import ConfigWindow
        app = QApplication(sys.argv)
        window = ConfigWindow()
        window.show()
        sys.exit(app.exec_())
    else:
        from app.core.automation import nexAds
        automation = nexAds()
        _AUTOMATION_INSTANCE = automation

        signal.signal(signal.SIGINT, _shutdown_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, _shutdown_handler)
        atexit.register(_shutdown_handler)

        try:
            automation.start()
        except KeyboardInterrupt:
            automation.stop()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    multiprocessing.set_start_method('spawn', force=True)
    main()
