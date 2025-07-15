import json
import os
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, 
                            QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, 
                            QSpinBox, QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, 
                            QFileDialog, QDoubleSpinBox, QRadioButton, QButtonGroup, QAction, 
                            QMessageBox, QSlider, QFrame)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QPalette, QColor, QKeySequence

class ConfigWindow(QMainWindow):
    def __init__(self, config_path='config.json'):
        super().__init__()
        self.config_path = config_path
        self.load_config()
        self.init_ui()
        self.set_dark_mode()

    def set_dark_mode(self):
        """Apply dark mode styling to the application."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2D2D2D;
            }
            QTabWidget::pane {
                border: 1px solid #444;
                background: #2D2D2D;
            }
            QTabBar::tab {
                background: #3D3D3D;
                color: #DDD;
                padding: 8px;
                border: 1px solid #444;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background: #505050;
            }
            QGroupBox {
                border: 1px solid #444;
                border-radius: 3px;
                margin-top: 10px;
                padding-top: 15px;
                color: #DDD;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
            }
            QLabel {
                color: #DDD;
            }
            QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background: #3D3D3D;
                color: #DDD;
                border: 1px solid #444;
                padding: 3px;
            }
            QPushButton {
                background: #505050;
                color: #DDD;
                border: 1px solid #444;
                padding: 5px;
            }
            QPushButton:hover {
                background: #606060;
            }
            QTableWidget {
                background: #3D3D3D;
                color: #DDD;
                gridline-color: #444;
            }
            QHeaderView::section {
                background: #505050;
                color: #DDD;
                padding: 5px;
                border: 1px solid #444;
            }
            QCheckBox {
                color: #DDD;
            }
            QRadioButton {
                color: #DDD;
            }
            QSlider::groove:horizontal {
                height: 8px;
                background: #444;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                width: 18px;
                height: 18px;
                background: #DDD;
                border-radius: 9px;
                margin: -5px 0;
            }
            QSlider::sub-page:horizontal {
                background: #42a5f5;
                border-radius: 4px;
            }
        """)

        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(45, 45, 45))
        dark_palette.setColor(QPalette.WindowText, Qt.white)
        dark_palette.setColor(QPalette.Base, QColor(35, 35, 35))
        dark_palette.setColor(QPalette.AlternateBase, QColor(45, 45, 45))
        dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
        dark_palette.setColor(QPalette.ToolTipText, Qt.white)
        dark_palette.setColor(QPalette.Text, Qt.white)
        dark_palette.setColor(QPalette.Button, QColor(80, 80, 80))
        dark_palette.setColor(QPalette.ButtonText, Qt.white)
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        QApplication.setPalette(dark_palette)

    def load_config(self):
        """Load configuration from JSON file or create default if not exists."""
        default_config = {
            "proxy": {
                "type": "http",
                "credentials": "",
                "file": ""
            },
            "browser": {
                "headless_mode": "virtual",
                "disable_ublock": True,
                "random_activity": True,
                "activities": ["scroll", "hover", "click"],
                "auto_accept_cookies": True,
                "prevent_redirects": True  # New config option for redirect prevention
            },
            "delay": {
                "min_time": 3,
                "max_time": 10
            },
            "session": {
                "enabled": False,
                "count": 0,
                "max_time": 30
            },
            "threads": 5,
            "os_fingerprint": ["windows", "macos", "linux"],
            "device_type": {
                "mobile": 0,
                "desktop": 100
            },
            "referrer": {
                "types": ["random"],
                "organic_keywords": "example\nsearch terms\nkeywords"
            },
            "urls": [
                {
                    "url": "https://example.com",
                    "random_page": False,
                    "min_time": 30,
                    "max_time": 60
                }
            ],
            "ads": {
                "ctr": 5.0,
                "min_time": 10,
                "max_time": 30
            }
        }

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
                # Ensure all keys exist in case config format changed
                for key, value in default_config.items():
                    if key not in self.config:
                        self.config[key] = value
                # Backward compatibility for old referrer format
                if "type" in self.config["referrer"]:
                    old_type = self.config["referrer"]["type"]
                    if old_type == "random":
                        self.config["referrer"]["types"] = ["random"]
                    else:
                        self.config["referrer"]["types"] = [old_type]
                    del self.config["referrer"]["type"]
            except:
                self.config = default_config
        else:
            self.config = default_config

    def save_config(self):
        """Save all configuration settings to file."""
        if self.save_config_file():
            self.statusBar().showMessage("Configuration saved successfully!", 3000)
        else:
            self.statusBar().showMessage("Error saving configuration!", 5000)

    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle('nexAds Configuration')
        self.setGeometry(100, 100, 1000, 700)

        # Main tab widget
        self.tabs = QTabWidget()
        
        # Create tabs
        self.general_tab = self.create_general_tab()
        self.url_tab = self.create_url_tab()
        self.ads_tab = self.create_ads_tab()
        
        # Add tabs to main widget
        self.tabs.addTab(self.general_tab, "General Settings")
        self.tabs.addTab(self.url_tab, "URL List")
        self.tabs.addTab(self.ads_tab, "Ads Settings")
        
        # Save button
        self.save_btn = QPushButton('Save Configuration')
        self.save_btn.clicked.connect(self.save_config)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        main_layout.addWidget(self.save_btn)
        
        # Central widget
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def create_general_tab(self):
        """Create the General Settings tab."""
        tab = QWidget()
        layout = QHBoxLayout()
        
        # Left column (40% width)
        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 10, 0)
        
        # Proxy Configuration
        proxy_group = QGroupBox("Proxy Configuration")
        proxy_layout = QVBoxLayout()
        
        self.proxy_type = QComboBox()
        self.proxy_type.addItems(["HTTP", "HTTPS", "SOCKS5", "SOCKS4"])
        self.proxy_type.setCurrentText(self.config["proxy"]["type"].upper())
        
        self.proxy_creds = QLineEdit()
        self.proxy_creds.setPlaceholderText("IP:Port or User:Pass@IP:Port")
        self.proxy_creds.setText(self.config["proxy"]["credentials"])
        
        self.proxy_file_btn = QPushButton("Load from File")
        self.proxy_file_btn.clicked.connect(self.load_proxy_file)
        
        self.proxy_file_label = QLabel(self.config["proxy"]["file"] or "No proxy file selected")
        
        proxy_layout.addWidget(QLabel("Proxy Type:"))
        proxy_layout.addWidget(self.proxy_type)
        proxy_layout.addWidget(QLabel("Proxy Credentials:"))
        proxy_layout.addWidget(self.proxy_creds)
        proxy_layout.addWidget(QLabel("OR"))
        proxy_layout.addWidget(self.proxy_file_btn)
        proxy_layout.addWidget(self.proxy_file_label)
        proxy_group.setLayout(proxy_layout)
        left_col.addWidget(proxy_group)
        
        # Browser Configuration
        browser_group = QGroupBox("Browser Configuration")
        browser_layout = QVBoxLayout()
        
        # Headless Mode
        headless_group = QGroupBox("Headless Mode")
        headless_layout = QVBoxLayout()
        
        self.headless_off = QRadioButton("Off (Visible)")
        self.headless_on = QRadioButton("Headless Mode")
        self.headless_virtual = QRadioButton("Virtual Mode")
        
        headless_btn_group = QButtonGroup()
        headless_btn_group.addButton(self.headless_off)
        headless_btn_group.addButton(self.headless_on)
        headless_btn_group.addButton(self.headless_virtual)
        
        if self.config["browser"]["headless_mode"] == "False":
            self.headless_off.setChecked(True)
        elif self.config["browser"]["headless_mode"] == "True":
            self.headless_on.setChecked(True)
        else:
            self.headless_virtual.setChecked(True)
        
        headless_layout.addWidget(self.headless_off)
        headless_layout.addWidget(self.headless_on)
        headless_layout.addWidget(self.headless_virtual)
        headless_group.setLayout(headless_layout)
        browser_layout.addWidget(headless_group)
        
        # Other browser settings
        self.disable_ublock = QCheckBox("Disable uBlock Add-on")
        self.disable_ublock.setChecked(self.config["browser"]["disable_ublock"])
        
        self.random_activity = QCheckBox("Enable Random Activity")
        self.random_activity.setChecked(self.config["browser"]["random_activity"])
        self.random_activity.stateChanged.connect(self.toggle_activity_options)
        
        self.auto_accept_cookies = QCheckBox("Auto Accept Google Cookies")
        self.auto_accept_cookies.setChecked(self.config["browser"]["auto_accept_cookies"])
        
        # New checkbox for redirect prevention
        self.prevent_redirects = QCheckBox("Prevent URL Redirects")
        self.prevent_redirects.setChecked(self.config["browser"].get("prevent_redirects", True))
        
        browser_layout.addWidget(self.disable_ublock)
        browser_layout.addWidget(self.random_activity)
        browser_layout.addWidget(self.auto_accept_cookies)
        browser_layout.addWidget(self.prevent_redirects)
        
        # Random Activity Options
        self.activity_options_group = QGroupBox("Random Activity Options")
        activity_options_layout = QVBoxLayout()
        
        self.scroll_check = QCheckBox("Random Scroll")
        self.hover_check = QCheckBox("Random Hover")
        self.click_check = QCheckBox("Random Click")
        self.mix_check = QCheckBox("Mix Random Activity")
        self.mix_check.stateChanged.connect(self.toggle_mix_activities)
        
        # Set initial states
        activities = self.config["browser"].get("activities", [])
        self.scroll_check.setChecked("scroll" in activities)
        self.hover_check.setChecked("hover" in activities)
        self.click_check.setChecked("click" in activities)
        self.mix_check.setChecked(len(activities) == 3)
        
        activity_options_layout.addWidget(self.scroll_check)
        activity_options_layout.addWidget(self.hover_check)
        activity_options_layout.addWidget(self.click_check)
        activity_options_layout.addWidget(self.mix_check)
        self.activity_options_group.setLayout(activity_options_layout)
        browser_layout.addWidget(self.activity_options_group)
        
        browser_group.setLayout(browser_layout)
        left_col.addWidget(browser_group)
        
        # Right column (60% width)
        right_col = QVBoxLayout()
        right_col.setContentsMargins(10, 0, 0, 0)
        
        # Delay Settings
        delay_group = QGroupBox("Delay Settings")
        delay_layout = QVBoxLayout()
        
        delay_layout.addWidget(QLabel("Min. Time (seconds):"))
        self.min_time = QSpinBox()
        self.min_time.setRange(1, 300)
        self.min_time.setValue(self.config["delay"]["min_time"])
        
        delay_layout.addWidget(self.min_time)
        
        delay_layout.addWidget(QLabel("Max. Time (seconds):"))
        self.max_time = QSpinBox()
        self.max_time.setRange(1, 300)
        self.max_time.setValue(self.config["delay"]["max_time"])
        delay_layout.addWidget(self.max_time)
        
        delay_group.setLayout(delay_layout)
        right_col.addWidget(delay_group)
        
        # Session Settings
        session_group = QGroupBox("Session Settings")
        session_layout = QVBoxLayout()
        
        self.session_enabled = QCheckBox("Enable Session Limit")
        self.session_enabled.setChecked(self.config["session"]["enabled"])
        self.session_enabled.stateChanged.connect(self.toggle_session_options)
        
        session_layout.addWidget(self.session_enabled)
        
        self.session_count = QSpinBox()
        self.session_count.setRange(0, 1000)  # 0 means unlimited
        self.session_count.setValue(self.config["session"]["count"])
        session_layout.addWidget(QLabel("Session Count (0=unlimited):"))
        session_layout.addWidget(self.session_count)
        
        self.session_max_time = QSpinBox()
        self.session_max_time.setRange(1, 1440)
        self.session_max_time.setValue(self.config["session"]["max_time"])
        session_layout.addWidget(QLabel("Max Session Time (minutes):"))
        session_layout.addWidget(self.session_max_time)
        
        session_group.setLayout(session_layout)
        right_col.addWidget(session_group)
        
        # Threads Settings
        threads_group = QGroupBox("Threads Settings")
        threads_layout = QVBoxLayout()
        
        self.threads = QSpinBox()
        self.threads.setRange(1, 100)
        self.threads.setValue(self.config["threads"])
        threads_layout.addWidget(QLabel("Number of Threads:"))
        threads_layout.addWidget(self.threads)
        
        threads_group.setLayout(threads_layout)
        right_col.addWidget(threads_group)
        
        # OS Fingerprint
        os_group = QGroupBox("OS Fingerprint")
        os_layout = QVBoxLayout()
        
        self.windows_check = QCheckBox("Windows")
        self.macos_check = QCheckBox("MacOS")
        self.linux_check = QCheckBox("Linux")
        
        # Set initial states
        os_list = self.config["os_fingerprint"]
        self.windows_check.setChecked("windows" in os_list)
        self.macos_check.setChecked("macos" in os_list)
        self.linux_check.setChecked("linux" in os_list)
        
        os_layout.addWidget(self.windows_check)
        os_layout.addWidget(self.macos_check)
        os_layout.addWidget(self.linux_check)
        os_group.setLayout(os_layout)
        right_col.addWidget(os_group)
        
        # Device Type Slider
        device_group = QGroupBox("Device Type")
        device_layout = QVBoxLayout()
        
        # Slider with labels
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(QLabel("Mobile"))
        
        self.device_slider = QSlider(Qt.Horizontal)
        self.device_slider.setRange(0, 100)
        self.device_slider.setValue(self.config["device_type"]["desktop"])  # Default to desktop
        self.device_slider.setTickPosition(QSlider.TicksBelow)
        self.device_slider.setTickInterval(10)
        
        slider_layout.addWidget(self.device_slider)
        slider_layout.addWidget(QLabel("Desktop"))
        
        # Percentage labels
        percent_layout = QHBoxLayout()
        self.mobile_percent = QLabel(f"Mobile: {100 - self.device_slider.value()}%")
        self.desktop_percent = QLabel(f"Desktop: {self.device_slider.value()}%")
        
        percent_layout.addWidget(self.mobile_percent, 0, Qt.AlignLeft)
        percent_layout.addWidget(self.desktop_percent, 0, Qt.AlignRight)
        
        device_layout.addLayout(slider_layout)
        device_layout.addLayout(percent_layout)
        device_group.setLayout(device_layout)
        right_col.addWidget(device_group)
        
        # Connect slider value change
        self.device_slider.valueChanged.connect(self.update_device_percentages)
        
        # Add columns to main layout
        layout.addLayout(left_col, 60)  # 40% width
        layout.addLayout(right_col, 40)  # 60% width
        tab.setLayout(layout)
        
        # Update activity options visibility
        self.toggle_activity_options()
        self.toggle_session_options()
        
        return tab

    def update_device_percentages(self, value):
        """Update the device percentage labels when slider moves."""
        self.mobile_percent.setText(f"Mobile: {100 - value}%")
        self.desktop_percent.setText(f"Desktop: {value}%")

    def create_url_tab(self):
        """Create the URL List tab with working delete functionality."""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Referrer Settings
        referrer_group = QGroupBox("Referrer Settings")
        referrer_layout = QVBoxLayout()
        
        self.direct_check = QCheckBox("Direct")
        self.social_check = QCheckBox("Social")
        self.organic_check = QCheckBox("Organic")
        self.random_check = QCheckBox("Random")
        
        # Set up connections for referrer checkboxes
        self.direct_check.stateChanged.connect(self.update_referrer_checks)
        self.social_check.stateChanged.connect(self.update_referrer_checks)
        self.organic_check.stateChanged.connect(self.update_referrer_checks)
        self.random_check.stateChanged.connect(self.update_referrer_checks)
        
        # Set initial states
        referrer_types = self.config["referrer"]["types"]
        if "random" in referrer_types:
            self.random_check.setChecked(True)
            self.direct_check.setChecked(True)
            self.social_check.setChecked(True)
            self.organic_check.setChecked(True)
        else:
            self.random_check.setChecked(False)
            self.direct_check.setChecked("direct" in referrer_types)
            self.social_check.setChecked("social" in referrer_types)
            self.organic_check.setChecked("organic" in referrer_types)
        
        referrer_type_layout = QHBoxLayout()
        referrer_type_layout.addWidget(self.direct_check)
        referrer_type_layout.addWidget(self.social_check)
        referrer_type_layout.addWidget(self.organic_check)
        referrer_type_layout.addWidget(self.random_check)
        referrer_layout.addLayout(referrer_type_layout)
        
        # Organic Keywords
        self.organic_keywords_input = QTextEdit()
        self.organic_keywords_input.setPlainText(self.config["referrer"]["organic_keywords"])
        referrer_layout.addWidget(QLabel("Organic Keywords (one per line):"))
        referrer_layout.addWidget(self.organic_keywords_input)
        
        referrer_group.setLayout(referrer_layout)
        layout.addWidget(referrer_group)
        
        # URL List
        url_list_group = QGroupBox("URL List")
        url_list_layout = QVBoxLayout()
        
        # URL Input
        url_input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter URL (use comma to separate multiple URLs for random selection)")
        self.add_url_btn = QPushButton("Add URL")
        self.add_url_btn.clicked.connect(self.add_url_to_table)
        self.url_input.returnPressed.connect(self.add_url_to_table)
        
        # Delete button - moved here next to Add button
        self.delete_url_btn = QPushButton("Delete URL")
        self.delete_url_btn.clicked.connect(self.delete_selected_url)
        
        url_input_layout.addWidget(self.url_input)
        url_input_layout.addWidget(self.add_url_btn)
        url_input_layout.addWidget(self.delete_url_btn)
        url_list_layout.addLayout(url_input_layout)
        
        # URL Table
        self.url_table = QTableWidget()
        self.url_table.setColumnCount(5)
        self.url_table.setHorizontalHeaderLabels(["#", "URL", "Random Page", "Min Time", "Max Time"])
        self.url_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.url_table.verticalHeader().setVisible(False)
        
        # Configure table for deletion
        self.url_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.url_table.setSelectionMode(QTableWidget.SingleSelection)
        self.url_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.url_table.installEventFilter(self)
        
        # Add keyboard shortcuts
        delete_action = QAction(self)
        delete_action.setShortcut(QKeySequence.Delete)
        delete_action.triggered.connect(self.delete_selected_url)
        self.addAction(delete_action)
        
        backspace_action = QAction(self)
        backspace_action.setShortcut(QKeySequence.Backspace)
        backspace_action.triggered.connect(self.delete_selected_url)
        self.addAction(backspace_action)
        
        # Populate table with existing URLs
        for i, url_data in enumerate(self.config["urls"], 1):
            self.add_url_to_table(url_data, i)
        
        url_list_layout.addWidget(self.url_table)
        
        url_list_group.setLayout(url_list_layout)
        layout.addWidget(url_list_group)
        
        tab.setLayout(layout)
        return tab

    def create_ads_tab(self):
        """Create the Ads Settings tab with compact layout."""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # CTR Settings - Compact version
        ctr_group = QGroupBox("CTR Settings")
        ctr_layout = QVBoxLayout()
        
        ctr_layout.addWidget(QLabel("CTR Percentage:"))
        self.ctr = QDoubleSpinBox()
        self.ctr.setRange(0.1, 100.0)
        self.ctr.setValue(self.config["ads"]["ctr"])
        ctr_layout.addWidget(self.ctr)
        
        ctr_group.setLayout(ctr_layout)
        layout.addWidget(ctr_group)
        
        # Ads Time Settings - Compact version
        ads_time_group = QGroupBox("Ads Time Settings")
        ads_time_layout = QVBoxLayout()
        
        ads_time_layout.addWidget(QLabel("Min. Time (seconds):"))
        self.ads_min_time = QSpinBox()
        self.ads_min_time.setRange(1, 300)
        self.ads_min_time.setValue(self.config["ads"]["min_time"])
        ads_time_layout.addWidget(self.ads_min_time)
        
        ads_time_layout.addWidget(QLabel("Max. Time (seconds):"))
        self.ads_max_time = QSpinBox()
        self.ads_max_time.setRange(1, 300)
        self.ads_max_time.setValue(self.config["ads"]["max_time"])
        ads_time_layout.addWidget(self.ads_max_time)
        
        ads_time_group.setLayout(ads_time_layout)
        layout.addWidget(ads_time_group)
        
        # Add stretch to push everything up
        layout.addStretch()
        
        tab.setLayout(layout)
        return tab

    def update_referrer_checks(self):
        """Update referrer checkboxes with the correct logic."""
        sender = self.sender()
        
        # If Random was checked
        if sender == self.random_check and self.random_check.isChecked():
            # Force all options on
            self.direct_check.setChecked(True)
            self.social_check.setChecked(True)
            self.organic_check.setChecked(True)
            return
        
        # If any individual option was unchecked while Random was checked
        if (self.random_check.isChecked() and 
            sender != self.random_check and 
            not sender.isChecked()):
            # Uncheck Random
            self.random_check.setChecked(False)
            return
        
        # If we're not dealing with Random changes
        if sender != self.random_check:
            # If all options are checked, auto-check Random
            if (self.direct_check.isChecked() and 
                self.social_check.isChecked() and 
                self.organic_check.isChecked()):
                self.random_check.setChecked(True)
            else:
                self.random_check.setChecked(False)

    def toggle_activity_options(self):
        """Show/hide random activity options based on checkbox state."""
        self.activity_options_group.setVisible(self.random_activity.isChecked())

    def toggle_mix_activities(self, state):
        """Check/uncheck all activity options when mix is toggled."""
        if state == Qt.Checked:
            self.scroll_check.setChecked(True)
            self.hover_check.setChecked(True)
            self.click_check.setChecked(True)
        elif not any([self.scroll_check.isChecked(), self.hover_check.isChecked(), self.click_check.isChecked()]):
            # Only uncheck if none are selected (to prevent infinite loop)
            self.mix_check.setChecked(False)

    def toggle_session_options(self):
        """Show/hide session options based on checkbox state."""
        self.session_count.setEnabled(self.session_enabled.isChecked())

    def load_proxy_file(self):
        """Open file dialog to load proxy list."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Proxy List", "", "Text Files (*.txt);;All Files (*)")
        if file_path:
            self.config["proxy"]["file"] = file_path
            self.proxy_creds.setText("")  # Clear credentials when using file
            self.proxy_file_label.setText(f"Loaded from: {file_path}")

    def add_url_to_table(self, url_data=None, row_num=None):
        """Add a URL to the table with numbering."""
        if url_data is None:
            url_text = self.url_input.text().strip()
            if not url_text:
                return
                
            urls = [u.strip() for u in url_text.split(',') if u.strip()]
            if not urls:
                return
                
            url_data = {
                "url": ",".join(urls),
                "random_page": len(urls) > 1,
                "min_time": 30,
                "max_time": 60
            }
            self.url_input.clear()
        
        row = self.url_table.rowCount()
        self.url_table.insertRow(row)
        
        # Numbering
        if row_num is None:
            row_num = row + 1
        num_item = QTableWidgetItem(str(row_num))
        num_item.setFlags(num_item.flags() ^ Qt.ItemIsEditable)
        self.url_table.setItem(row, 0, num_item)
        
        # URL
        url_item = QTableWidgetItem(url_data["url"])
        self.url_table.setItem(row, 1, url_item)
        
        # Random Page checkbox
        random_check = QCheckBox()
        random_check.setChecked(url_data["random_page"])
        random_check.setStyleSheet("margin-left:50%; margin-right:50%;")
        self.url_table.setCellWidget(row, 2, random_check)
        
        # Min Time
        min_time = QSpinBox()
        min_time.setRange(1, 3600)
        min_time.setValue(url_data["min_time"])
        self.url_table.setCellWidget(row, 3, min_time)
        
        # Max Time
        max_time = QSpinBox()
        max_time.setRange(1, 3600)
        max_time.setValue(url_data["max_time"])
        self.url_table.setCellWidget(row, 4, max_time)
        
        # Update numbering for all rows
        self.update_table_numbering()

    def update_table_numbering(self):
        """Update the numbering column in the URL table."""
        for row in range(self.url_table.rowCount()):
            num_item = QTableWidgetItem(str(row + 1))
            num_item.setFlags(num_item.flags() ^ Qt.ItemIsEditable)
            self.url_table.setItem(row, 0, num_item)

    def delete_selected_url(self):
        """Delete selected URL from the table with proper keyboard support."""
        selected_rows = {index.row() for index in self.url_table.selectedIndexes()}
        if not selected_rows:
            return
            
        # Delete rows from bottom to top to maintain correct indices
        for row in sorted(selected_rows, reverse=True):
            self.url_table.removeRow(row)
        
        # Update numbering for remaining rows
        self.update_table_numbering()

    def eventFilter(self, source, event):
        """Handle keyboard events for the URL table."""
        if event.type() == event.KeyPress and source is self.url_table:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.delete_selected_url()
                return True
        return super().eventFilter(source, event)

    def save_config_file(self):
        """Save the current configuration to file."""
        try:
            # Create an OrderedDict to maintain the desired order
            from collections import OrderedDict
            config = OrderedDict()
            
            # Proxy settings
            config["proxy"] = {
                "type": self.proxy_type.currentText().lower(),
                "credentials": self.proxy_creds.text(),
                "file": self.config["proxy"]["file"]  # Keep existing file path
            }
            
            # Validate proxy settings - only one of credentials or file can be set
            if config["proxy"]["credentials"] and config["proxy"]["file"]:
                QMessageBox.warning(self, "Proxy Conflict", 
                                "Both proxy credentials and file are specified. Using credentials and ignoring file.")
                config["proxy"]["file"] = ""
            
            # Browser settings
            config["browser"] = OrderedDict()
            if self.headless_off.isChecked():
                config["browser"]["headless_mode"] = "False"
            elif self.headless_on.isChecked():
                config["browser"]["headless_mode"] = "True"
            else:
                config["browser"]["headless_mode"] = "virtual"
                
            config["browser"]["disable_ublock"] = self.disable_ublock.isChecked()
            config["browser"]["random_activity"] = self.random_activity.isChecked()
            config["browser"]["auto_accept_cookies"] = self.auto_accept_cookies.isChecked()
            config["browser"]["prevent_redirects"] = self.prevent_redirects.isChecked()  # Save redirect prevention setting
            
            # Random activities
            activities = []
            if self.scroll_check.isChecked():
                activities.append("scroll")
            if self.hover_check.isChecked():
                activities.append("hover")
            if self.click_check.isChecked():
                activities.append("click")
            config["browser"]["activities"] = activities
            
            # Delay settings
            config["delay"] = {
                "min_time": self.min_time.value(),
                "max_time": self.max_time.value()
            }
            
            # Session settings
            config["session"] = {
                "enabled": self.session_enabled.isChecked(),
                "count": self.session_count.value(),
                "max_time": self.session_max_time.value()
            }
            
            # Threads
            config["threads"] = self.threads.value()
            
            # OS fingerprint
            os_list = []
            if self.windows_check.isChecked():
                os_list.append("windows")
            if self.macos_check.isChecked():
                os_list.append("macos")
            if self.linux_check.isChecked():
                os_list.append("linux")
            config["os_fingerprint"] = os_list
            
            # Device type - now right after os_fingerprint
            desktop_percent = self.device_slider.value()
            config["device_type"] = {
                "mobile": 100 - desktop_percent,
                "desktop": desktop_percent
            }
            
            # Referrer settings
            referrer_types = []
            if self.random_check.isChecked():
                referrer_types = ["random"]
            else:
                if self.direct_check.isChecked():
                    referrer_types.append("direct")
                if self.social_check.isChecked():
                    referrer_types.append("social")
                if self.organic_check.isChecked():
                    referrer_types.append("organic")
            config["referrer"] = {
                "types": referrer_types,
                "organic_keywords": self.organic_keywords_input.toPlainText()
            }
            
            # URL list
            config["urls"] = []
            for row in range(self.url_table.rowCount()):
                url_data = {
                    "url": self.url_table.item(row, 1).text(),
                    "random_page": self.url_table.cellWidget(row, 2).isChecked(),
                    "min_time": self.url_table.cellWidget(row, 3).value(),
                    "max_time": self.url_table.cellWidget(row, 4).value()
                }
                config["urls"].append(url_data)
            
            # Ads settings
            config["ads"] = {
                "ctr": self.ctr.value(),
                "min_time": self.ads_min_time.value(),
                "max_time": self.ads_max_time.value()
            }
            
            # Save to file
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving config file: {str(e)}")
            return False