"""
nexads/ui/config_window.py
PyQt5 ConfigWindow — main class with UI layout, widget callbacks, event handlers.
"""

from collections import OrderedDict

from PyQt5.QtWidgets import (QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
                            QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
                            QSpinBox, QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
                            QFileDialog, QDoubleSpinBox, QRadioButton, QButtonGroup, QAction,
                            QMessageBox, QSlider, QFrame, QScrollArea, QListWidget, QListWidgetItem,
                            QAbstractItemView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence

from app.ui.config_theme import apply_dark_mode
from app.ui.config_io import load_config, write_config

class ConfigWindow(QMainWindow):
    def __init__(self, config_path='config.json'):
        super().__init__()
        self.config_path = config_path
        self.config = load_config(config_path)
        self.init_ui()
        apply_dark_mode(self)

    def save_config(self):
        """Save all configuration settings to file."""
        if self.save_config_file():
            self.statusBar().showMessage("Configuration saved successfully!", 3000)
        else:
            self.statusBar().showMessage("Error saving configuration!", 5000)

    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle('nexAds Configuration')
        self.setGeometry(80, 70, 1220, 820)
        self.setMinimumSize(1080, 760)

        # Main tab widget
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        
        # Create tabs
        self.general_tab = self.wrap_in_scroll_area(self.create_general_tab())
        self.url_tab = self.wrap_in_scroll_area(self.create_url_tab())
        self.ads_tab = self.wrap_in_scroll_area(self.create_ads_tab())
        
        # Add tabs to main widget
        self.tabs.addTab(self.general_tab, "General Settings")
        self.tabs.addTab(self.url_tab, "URL List")
        self.tabs.addTab(self.ads_tab, "Ads Settings")
        
        # Save button
        self.save_btn = QPushButton('Save Configuration')
        self.save_btn.clicked.connect(self.save_config)
        self.save_btn.setMinimumHeight(36)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 10)
        main_layout.setSpacing(10)
        main_layout.addWidget(self.tabs)
        main_layout.addWidget(self.save_btn)
        
        # Central widget
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def wrap_in_scroll_area(self, content_widget: QWidget):
        """Wrap a tab content widget in a scroll area so content is never clipped."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(content_widget)
        return scroll

    def create_general_tab(self):
        """Create the General Settings tab."""
        tab = QWidget()
        layout = QHBoxLayout()
        layout.setSpacing(14)
        
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
        
        self.session_min_time = QSpinBox()
        self.session_min_time.setRange(0, 1440)
        self.session_min_time.setValue(self.config["session"].get("min_time", 0))
        session_layout.addWidget(QLabel("Min Session Time (minutes, 0=disabled):"))
        session_layout.addWidget(self.session_min_time)

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
        layout.addLayout(left_col, 40)   # 40% width
        layout.addLayout(right_col, 60)  # 60% width
        left_col.addStretch(1)
        right_col.addStretch(1)
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
        layout.setSpacing(12)
        
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
        self.add_url_btn.clicked.connect(lambda: self.add_url_to_table())
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
        self.url_table.horizontalHeader().setMinimumHeight(34)
        self.url_table.verticalHeader().setDefaultSectionSize(34)
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
        """Create the Ads Settings tab with multi-provider support."""
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(12)

        # CTR Settings
        ctr_group = QGroupBox("CTR Settings")
        ctr_layout = QVBoxLayout()

        ctr_layout.addWidget(QLabel("CTR Percentage:"))
        self.ctr = QDoubleSpinBox()
        self.ctr.setRange(0.1, 100.0)
        self.ctr.setValue(self.config["ads"]["ctr"])
        ctr_layout.addWidget(self.ctr)

        ctr_group.setLayout(ctr_layout)
        layout.addWidget(ctr_group)

        # Ad Providers
        providers_group = QGroupBox("Ad Providers")
        providers_layout = QVBoxLayout()

        self.adsense_provider_check = QCheckBox("AdSense")
        self.adsterra_provider_check = QCheckBox("Adsterra")

        providers_cfg = self.config["ads"].get("providers", ["adsense"])
        self.adsense_provider_check.setChecked("adsense" in providers_cfg)
        self.adsterra_provider_check.setChecked("adsterra" in providers_cfg)

        self.adsense_provider_check.stateChanged.connect(self._update_provider_order_list)
        self.adsterra_provider_check.stateChanged.connect(self._update_provider_order_list)

        providers_layout.addWidget(self.adsense_provider_check)
        providers_layout.addWidget(self.adsterra_provider_check)
        providers_group.setLayout(providers_layout)
        layout.addWidget(providers_group)

        # Ad Strategy
        strategy_group = QGroupBox("Ad Strategy")
        strategy_layout = QVBoxLayout()

        strategy_layout.addWidget(QLabel("Strategy:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["First Success", "One Per Provider"])

        current_strategy = self.config["ads"].get("strategy", "first_success")
        self.strategy_combo.setCurrentIndex(1 if current_strategy == "one_per_provider" else 0)
        self.strategy_combo.currentIndexChanged.connect(self._toggle_provider_order)

        strategy_layout.addWidget(self.strategy_combo)
        strategy_group.setLayout(strategy_layout)
        layout.addWidget(strategy_group)

        # Provider Priority Order (drag-and-drop)
        self.provider_order_group = QGroupBox("Provider Priority Order (drag to reorder)")
        order_layout = QVBoxLayout()

        self.provider_order_list = QListWidget()
        self.provider_order_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.provider_order_list.setDefaultDropAction(Qt.MoveAction)
        self.provider_order_list.setMinimumHeight(80)
        self.provider_order_list.setMaximumHeight(120)

        order_layout.addWidget(self.provider_order_list)
        self.provider_order_group.setLayout(order_layout)
        layout.addWidget(self.provider_order_group)

        # Populate order list from config and set visibility
        self._update_provider_order_list()
        self._toggle_provider_order()

        # Ads Time Settings
        ads_time_group = QGroupBox("Ad Landing Stay Time")
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

        layout.addStretch()

        tab.setLayout(layout)
        return tab

    def _update_provider_order_list(self):
        """Update the provider order list based on checked providers."""
        _key_to_display = {"adsense": "AdSense", "adsterra": "Adsterra"}
        _display_to_key = {"AdSense": "adsense", "Adsterra": "adsterra"}

        # Remember current widget order
        current_order = []
        for i in range(self.provider_order_list.count()):
            display = self.provider_order_list.item(i).text()
            current_order.append(_display_to_key.get(display, display.lower()))

        # On first load, use config order
        if not current_order:
            current_order = self.config["ads"].get("providers", ["adsense"])

        # Enabled providers
        enabled = set()
        if self.adsense_provider_check.isChecked():
            enabled.add("adsense")
        if self.adsterra_provider_check.isChecked():
            enabled.add("adsterra")

        # Preserve order for still-enabled, add new ones alphabetically
        ordered = [p for p in current_order if p in enabled]
        for p in sorted(enabled):
            if p not in ordered:
                ordered.append(p)

        self.provider_order_list.clear()
        for p in ordered:
            item = QListWidgetItem(_key_to_display.get(p, p))
            self.provider_order_list.addItem(item)

    def _toggle_provider_order(self):
        """Show provider order only when strategy is First Success."""
        is_first_success = self.strategy_combo.currentIndex() == 0
        self.provider_order_group.setVisible(is_first_success)

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
        else:
            # Unchecking Mix clears all sub-options so state stays in sync
            self.scroll_check.setChecked(False)
            self.hover_check.setChecked(False)
            self.click_check.setChecked(False)

    def toggle_session_options(self):
        """Show/hide session options based on checkbox state."""
        enabled = self.session_enabled.isChecked()
        self.session_count.setEnabled(enabled)
        self.session_min_time.setEnabled(enabled)
        self.session_max_time.setEnabled(enabled)

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
            
            # Session settings
            config["session"] = {
                "enabled": self.session_enabled.isChecked(),
                "count": self.session_count.value(),
                "min_time": self.session_min_time.value(),
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
            
            # Ads settings — build ordered provider list from drag-and-drop widget
            _display_to_key = {"AdSense": "adsense", "Adsterra": "adsterra"}
            providers = []
            for i in range(self.provider_order_list.count()):
                display = self.provider_order_list.item(i).text()
                providers.append(_display_to_key.get(display, display.lower()))

            strategy = "first_success" if self.strategy_combo.currentIndex() == 0 else "one_per_provider"

            config["ads"] = {
                "ctr": self.ctr.value(),
                "providers": providers,
                "strategy": strategy,
                "min_time": self.ads_min_time.value(),
                "max_time": self.ads_max_time.value()
            }

            # --- Validate min <= max before saving ---
            errors = []
            if config["ads"]["min_time"] > config["ads"]["max_time"]:
                errors.append("Ads time: min time must be ≤ max time")
            if config["session"].get("min_time", 0) > 0 and config["session"]["min_time"] > config["session"]["max_time"]:
                errors.append("Session: min time must be ≤ max time")
            for i, url_data in enumerate(config["urls"]):
                if url_data["min_time"] > url_data["max_time"]:
                    errors.append(f"URL row {i + 1}: min time must be ≤ max time")
            if errors:
                QMessageBox.warning(self, "Validation Error", "\n".join(errors))
                return False
            
            return write_config(self.config_path, config)
        except Exception as e:
            print(f"Error saving config file: {str(e)}")
            return False
