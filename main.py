"""
main.py — nexAds entry point.

Usage:
  python main.py           # run automation
  python main.py --config  # open configuration GUI
"""

import sys
import multiprocessing
from argparse import ArgumentParser


def main():
    parser = ArgumentParser(description='nexAds Automation Tool')
    parser.add_argument('--config', action='store_true', help='Open configuration GUI')
    args = parser.parse_args()

    if args.config:
        from PyQt5.QtWidgets import QApplication
        from nexads.ui.config_window import ConfigWindow
        app = QApplication(sys.argv)
        window = ConfigWindow()
        window.show()
        sys.exit(app.exec_())
    else:
        from nexads.core.automation import nexAds
        automation = nexAds()
        try:
            automation.start()
        except KeyboardInterrupt:
            automation.stop()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    multiprocessing.set_start_method('spawn', force=True)
    main()
