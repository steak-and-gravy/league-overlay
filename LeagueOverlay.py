import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
import irsdk
import threading
import time
import json
import os
import yaml
from datetime import datetime

class leagueOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.ir = irsdk.IRSDK()
        self.is_connected = False
        self.running = True
        self.drag_data = {"x": 0, "y": 0}
        
        # Auto-centering variables
        self.player_car_idx = None
        self.last_manual_scroll = 0
        self.manual_scroll_timeout = 5  # seconds
        self.auto_center_enabled = True
        self.status_hide_timer = None
        
        self.show_only_my_division = False
        self.opacity = 0.8
        self.width = 350
        self.height = 320
        self.x = (self.root.winfo_screenwidth() // 2) - (self.width // 2)
        self.y = (self.root.winfo_screenheight() // 2) - (self.height // 2)
        self.allow_resize = False
        self.hide_headers = False
        self.center_drivers = False
        self.hide_timer = None
        self.show_timer = None
        self.top_elements_visible = True
        self.current_division_filter = None  # None means show all, otherwise division name
        self.division_cycle_order = ["Pro", "ProAm", "Am", "Rookie","All"]  # Order to cycle through

        # Color coding data
        self.color_config_file = "league_divisions.json"
        self.settings_file = "BB_League_Overlay.config"
        self.driver_colors = self.load_color_config()
        self.load_settings()
        self.setup_window()
        
        # Division colors
        self.default_colors = {
            "Pro": "#FF8C00",
            "ProAm": "#9370DB", 
            "Am": "#45B3E0",
            "Rookie": "#FF2000",
            "Default": "#FFFFFF"
        }
        self.available_colors = self.load_division_colors()
        
        self.setup_gui()
        self.setup_drag_functionality()
        self.setup_scroll_functionality()
        
        # Start telemetry thread
        self.telemetry_thread = threading.Thread(target=self.telemetry_loop, daemon=True)
        self.telemetry_thread.start()
        
        # Start GUI update thread
        self.gui_thread = threading.Thread(target=self.update_gui, daemon=True)
        self.gui_thread.start()
        
        self.race_data = []
        self.displayed_data = []  # Track what's currently displayed
        self.data_widgets = {}    # Store widget references
        self.context_menu = None
        
    def setup_window(self):
        """Configure the main window"""
        self.root.title("BB's League Overlay")
        self.root.geometry(f"{self.width}x{self.height}+{self.x}+{self.y}")
            
        # Make window transparent and always on top
        self.root.attributes('-alpha', self.opacity)
        self.root.attributes('-topmost', True)
        self.root.configure(bg='black')
        
        if self.allow_resize:
            # Enable resizing
            self.root.resizable(True, True)

            # Enable resizing but disable maximize
            self.root.resizable(True, True)
            self.root.attributes('-toolwindow', True)  # This removes maximize button on Windows

            # For cross-platform compatibility, you can also use:
            # On Windows, this will disable maximize:
            try:
                self.root.wm_attributes('-toolwindow', True)
            except:
                pass  # Ignore if not supported on this platform

            # Override maximize behavior
            def disable_maximize(event=None):
                return "break"

            self.root.bind("<Double-Button-1>", disable_maximize)  # Disable double-click maximize
            self.root.bind("<F11>", disable_maximize)  # Disable F11 fullscreen
        else:
            # Remove window decorations for overlay effect
            self.root.overrideredirect(True)

        # Set minimum window size
        self.root.minsize(320, 220)
        
        # Save position when window is moved
        self.root.bind('<Configure>', self.on_window_configure)
        
    def setup_gui(self):
        """Setup the GUI elements"""
        # Main frame
        self.main_frame = tk.Frame(self.root, bg='black')
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title bar for dragging
        self.title_bar = tk.Frame(self.main_frame, bg='#333333', height=30)
        self.title_bar.pack(fill=tk.X)
        self.title_bar.pack_propagate(False)
        
        # Title label
        title_text = ""
        if not self.allow_resize:
            title_text = "BB's League Overlay"
        self.title_label = tk.Label(self.title_bar, text=title_text, 
                                   fg='white', bg='#333333', font=('Arial', 10, 'bold'))
        self.title_label.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Control buttons
        self.button_frame = tk.Frame(self.title_bar, bg='#333333')
        self.button_frame.pack(side=tk.RIGHT, padx=5, pady=2)
        self.division_filter_btn = tk.Button(self.button_frame, text="All Divisons", command=self.toggle_division_filter,
                                 bg='#555555', fg='white', font=('Arial', 8))
        self.division_filter_btn.pack(side=tk.LEFT, padx=2)
        
        self.load_config_btn = tk.Button(self.button_frame, text="Load", command=self.load_different_config,
                                       bg='#555555', fg='white', font=('Arial', 8))
        self.load_config_btn.pack(side=tk.LEFT, padx=2)

        self.new_config_btn = tk.Button(self.button_frame, text="New", command=self.create_new_config,
                                       bg='#555555', fg='white', font=('Arial', 8))
        self.new_config_btn.pack(side=tk.LEFT, padx=2)
        
        self.close_btn = tk.Button(self.button_frame, text="×", command=self.close_application,
                                  bg='#cc0000', fg='white', font=('Arial', 8), width=3)
        if not self.allow_resize:
            self.close_btn.pack(side=tk.LEFT, padx=2)
        
        # Status label
        self.status_label = tk.Label(self.main_frame, text="Connecting to iRacing...", 
                                    fg='yellow', bg='black', font=('Arial', 9))
        self.status_label.pack(pady=5)
        
        # Fixed header frame
        self.header_frame = tk.Frame(self.main_frame, bg='#333333')
        self.header_frame.pack(fill=tk.X, pady=2)
        
        # Scrollable frame for race data
        self.canvas_frame = tk.Frame(self.main_frame, bg='black')
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg='black', highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.canvas_frame, orient="vertical", command=self.on_scrollbar)
        self.scrollable_frame = tk.Frame(self.canvas, bg='black')
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        def configure_scroll_region(event=None):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            canvas_width = self.canvas.winfo_width()
            if canvas_width > 1: # Ensure canvas is initialized
                self.canvas.itemconfig(self.canvas.find_all()[0], width=canvas_width)
        
        self.scrollable_frame.bind('<Configure>', configure_scroll_region)
        self.canvas.bind('<Configure>', configure_scroll_region)

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        if self.hide_headers:
            self.hide_top_elements()
            self.focus_bindings(True)
            

    def focus_bindings(self, isEnable=True):
        """Add or Remove focus event bindings for hide/show functionality"""
        if self.hide_headers:
            if isEnable:
                self.root.bind("<FocusIn>", self.on_focus_in)
                self.root.bind("<FocusOut>", self.on_focus_out)
            else:
                self.root.unbind("<FocusIn>")
                self.root.unbind("<FocusOut>")
        
    def create_headers(self):
        """Create column headers in the fixed header frame using grid"""
        # Clear existing headers
        for widget in self.header_frame.winfo_children():
            widget.destroy()
        
        # Get dynamic sizes
        sizes = self.get_dynamic_column_sizes(is_header=True)
        
        # Configure grid with dynamic sizes and uniform groups
        self.header_frame.grid_columnconfigure(0, weight=sizes['gap'], minsize=sizes['pos'], uniform="col0")
        self.header_frame.grid_columnconfigure(1, weight=sizes['class_pos'], minsize=sizes['class_pos'], uniform="col1")
        self.header_frame.grid_columnconfigure(2, weight=sizes['car_num'], minsize=sizes['car_num'], uniform="col2")
        self.header_frame.grid_columnconfigure(3, weight=sizes['driver'], minsize=sizes['driver'], uniform="col3")
        self.header_frame.grid_columnconfigure(4, weight=sizes['gap'], minsize=sizes['gap'], uniform="col4")
        
        headers = ["Pos", "C-Pos", "Car#", "Driver", "Div Gap"]
        
        for i, header in enumerate(headers):
            label = tk.Label(self.header_frame, text=header, fg='white', bg='#333333',
                            font=('Arial', 9, 'bold'))
            label.grid(row=0, column=i, sticky='ew', padx=2)

    def toggle_division_filter(self):
        """Cycle through division filters or toggle My Division if player is on track"""
        # Check if player is on track
        player_on_track = self.player_car_idx is not None and any(
            d['car_idx'] == self.player_car_idx for d in self.race_data
        )
        
        if player_on_track:
            # Original behavior - toggle My Division
            self.show_only_my_division = not self.show_only_my_division
            self.current_division_filter = None
            button_text = "My Division" if self.show_only_my_division else "All Divisions"
            button_color = "#0FC436" if self.show_only_my_division else '#555555'
        else:
            # Cycle through divisions
            self.show_only_my_division = False
            
            # Get divisions that have drivers (excluding "All" and "Default")
            divisions_with_drivers = set()
            for driver_data in self.race_data:
                driver_color = self.get_driver_color(driver_data['driver_name'])
                for div_name, div_color in self.available_colors.items():
                    if div_color == driver_color and div_name not in ["Default", "All"]:
                        divisions_with_drivers.add(div_name)
            
            # Always include "All" as an option
            available_options = [div for div in self.division_cycle_order 
                            if div == "All" or div in divisions_with_drivers]
            
            # Find next option in cycle
            if self.current_division_filter is None:
                # Start with first available option
                next_filter = available_options[0] if available_options else "All"
            else:
                # Find current filter index and get next
                try:
                    if self.current_division_filter == "All":
                        current_name = "All"
                    else:
                        current_name = self.current_division_filter
                    
                    current_idx = available_options.index(current_name)
                    # Get next option, wrapping around if at end
                    next_idx = (current_idx + 1) % len(available_options)
                    next_filter = available_options[next_idx]
                except (ValueError, IndexError):
                    # Current filter not found, start from beginning
                    next_filter = available_options[0] if available_options else "All"
            
            # Set the filter
            if next_filter == "All":
                self.current_division_filter = None
                button_text = "All Divisions"
                button_color = '#555555'
            else:
                self.current_division_filter = next_filter
                button_text = next_filter
                button_color = self.available_colors[next_filter]
        
        self.division_filter_btn.config(text=button_text, bg=button_color)
        self.canvas.yview_moveto(0.0) # make sure to scroll to top when changing views
    
    def setup_drag_functionality(self):
        """Setup window dragging"""
        self.title_bar.bind("<ButtonPress-1>", self.start_drag)
        self.title_bar.bind("<B1-Motion>", self.drag_window)
        self.title_label.bind("<ButtonPress-1>", self.start_drag)
        self.title_label.bind("<B1-Motion>", self.drag_window)
        
    def setup_scroll_functionality(self):
        """Setup mouse wheel scrolling"""
        # Bind mouse wheel to canvas and all child widgets
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Button-4>", self.on_mousewheel)  # Linux
        self.canvas.bind("<Button-5>", self.on_mousewheel)  # Linux
        
        # Also bind to the main window so scrolling works anywhere
        self.root.bind("<MouseWheel>", self.on_mousewheel)
        self.root.bind("<Button-4>", self.on_mousewheel)
        self.root.bind("<Button-5>", self.on_mousewheel)
        
    def on_mousewheel(self, event):
        """Handle mouse wheel scrolling"""
        # Mark as manual scroll
        self.last_manual_scroll = time.time()
        
        # Determine scroll direction and amount
        if event.delta:  # Windows
            delta = -1 * (event.delta / 120)
        else:  # Linux
            delta = -1 if event.num == 4 else 1
            
        # Scroll the canvas
        self.canvas.yview_scroll(int(delta), "units")
        
    def start_drag(self, event):
        """Start dragging the window"""
        self.drag_data["x"] = event.x
        self.drag_data["y"] = event.y
        
    def on_scrollbar(self, *args):
        """Handle scrollbar scrolling"""
        # Mark as manual scroll to prevent auto-centering
        self.last_manual_scroll = time.time()
        # Let the scrollbar do its normal scrolling
        self.canvas.yview(*args)

    def drag_window(self, event):
        """Drag the window"""
        x = self.root.winfo_x() + event.x - self.drag_data["x"]
        y = self.root.winfo_y() + event.y - self.drag_data["y"]
        self.root.geometry(f"+{x}+{y}")

    def on_focus_in(self, event):
        """Handle window gaining focus"""
        if self.hide_headers:
            # Cancel hide timer if active
            if self.hide_timer:
                self.root.after_cancel(self.hide_timer)
                self.hide_timer = None
            
            # Show top elements if hidden
            if not self.top_elements_visible:
                self.show_top_elements()

    def on_focus_out(self, event):
        """Handle window losing focus"""
        if self.hide_headers:
            # Cancel any existing hide timer
            if self.hide_timer:
                self.root.after_cancel(self.hide_timer)
            
        # Start hide timer with 500ms delay
        self.hide_timer = self.root.after(500, self.hide_top_elements)

    def hide_top_elements(self):
        """Hide the title bar and status label"""
        if self.top_elements_visible:
            self.title_bar.pack_forget()
            self.status_label.pack_forget()
            self.top_elements_visible = False
            self.hide_timer = None
            self.root.overrideredirect(True)

    def show_top_elements(self):
        """Show the title bar and status label"""
        if not self.top_elements_visible:
            self.title_bar.pack(fill=tk.X, before=self.header_frame)
            if not self.is_connected or not hasattr(self, 'status_hide_timer') or not self.status_hide_timer:
                self.status_label.pack(pady=5, before=self.header_frame)
            if self.allow_resize:
                # Enable resizing
                self.root.overrideredirect(False)
            self.top_elements_visible = True
        
        
    def close_application(self):
        """Close the application"""
            # Cancel any pending timers
        if self.hide_timer:
            self.root.after_cancel(self.hide_timer)
        if self.show_timer:
            self.root.after_cancel(self.show_timer)

        self.save_settings()  # Save position before closing
        self.running = False
        self.root.destroy()
        
    def load_color_config(self):
        """Load division color configuration from file"""
        if os.path.exists(self.color_config_file):
            try:
                with open(self.color_config_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def create_new_config(self):
        """Create a new color configuration file"""
        self.focus_bindings(False)
        from tkinter import filedialog, messagebox
        
        # Ask user where to save the new config file
        file_path = filedialog.asksaveasfilename(
            title="Create New League Config File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=".",
            defaultextension=".json"
        )
        
        if file_path:
            try:
                # Create empty config file
                empty_config = {}
                with open(file_path, 'w') as f:
                    json.dump(empty_config, f, indent=2)
                
                # Load the new empty config
                self.driver_colors = empty_config
                self.color_config_file = file_path
                self.save_settings()  # Save the new config file path
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create config file: {e}")
        self.focus_bindings(True)
    
    def load_settings(self):
        """Load window position and last config file and everything else from settings"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    # Load last used color config file if it exists
                    league_config = data.get('league_config')
                    if league_config and os.path.exists(league_config):
                        self.color_config_file = league_config
                        self.driver_colors = self.load_color_config()
                    if data.get('opacity'):
                        self.opacity = data.get('opacity')
                    if data.get('x'):
                        self.x = data.get('x')
                    if data.get('y'):
                        self.y = data.get('y')
                    if data.get('height'):
                        self.height = data.get('height')
                    if data.get('width'):
                        self.width = data.get('width')
                    if data.get('allow_resize'):
                        try: 
                            self.allow_resize = data.get('allow_resize')
                        except:
                            pass
                    if data.get('hide'):
                        try:
                            self.hide_headers = data.get('hide')
                        except:
                            pass
                    if data.get('center_drivers'):
                        try:
                            self.center_drivers = data.get('center_drivers')
                        except:
                            pass
            except:
                pass
        return None

    def load_division_colors(self):
        """Load division colors from settings file or use defaults"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    division_colors = data.get('division_colors', {})
                    # Merge with defaults - use saved colors if available, defaults otherwise
                    colors = self.default_colors.copy()
                    colors.update(division_colors)
                    return colors
            except:
                pass
        return self.default_colors.copy()
    
    def save_settings(self):
        """Save window position, last config file, and division colors to settings"""
        try:
            settings = {
                'league_config': self.color_config_file,
                'division_colors': self.available_colors,
                'x': self.root.winfo_x(), 
                'y': self.root.winfo_y(),
                'height': self.root.winfo_height(),
                'width': self.root.winfo_width(),
                'opacity': self.opacity,
                'allow_resize': self.allow_resize,
                'hide': self.hide_headers,
                'center_drivers': self.center_drivers
            }
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")
    
    def on_window_configure(self, event):
        """Handle window configuration changes"""
        if event.widget == self.root:
            # Refresh layout when window is resized
            self.root.after(100, self.refresh_layout)
            # Save position after a short delay to avoid too many writes
            self.root.after(1000, self.save_settings)
        
    def save_color_config(self):
        """Save color configuration to file"""
        try:
            with open(self.color_config_file, 'w') as f:
                json.dump(self.driver_colors, f, indent=2)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save color config: {e}")
            
    def create_context_menu(self, driver_name):
        """Create context menu for driver division selection"""
        if self.context_menu:
            self.context_menu.destroy()
    
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Change Division", state="disabled")
        self.context_menu.add_separator()
    
        for division_name in self.available_colors.keys():
            self.context_menu.add_command(
                label=division_name,
                command=lambda c=division_name: self.set_driver_division(driver_name, c)
            )
    
        return self.context_menu

    def set_driver_division(self, driver_name, division_name):
        """Set driver division and save configuration"""
        key = driver_name
        if division_name == "Default":
            # Remove from config instead of setting to Default
            if key in self.driver_colors:
                del self.driver_colors[key]
        else:
            # Set the division normally
            self.driver_colors[key] = division_name
        self.save_color_config()

        # Immediately update the display for this driver
        self.update_driver_row_color(driver_name)

        # Hide context menu
        if self.context_menu:
            self.context_menu.unpost()

    def update_driver_row_color(self, driver_name):
        """Immediately update the color of a specific driver's row"""
        # Find the driver in current displayed data
        for driver_data in self.displayed_data:
            if driver_data['driver_name'] == driver_name:
                car_idx = driver_data['car_idx']
                if car_idx in self.data_widgets:
                    widgets = self.data_widgets[car_idx]
                    
                    # Get the new color
                    new_color = self.get_driver_color(driver_name)
                    
                    # Update all color-dependent widgets in the row
                    bg_color = '#1a1a1a' if driver_data['is_player'] else 'black'
                    font_weight = 'bold' if driver_data['is_player'] else 'normal'
                    
                    widgets['position'].config(fg=new_color)
                    widgets['division_position'].config(fg=new_color)
                    widgets['car_number'].config(fg=new_color)
                    widgets['name'].config(fg=new_color)
                    
                break

    def show_context_menu(self, event, driver_name):
        """Show context menu at cursor position"""
        menu = self.create_context_menu(driver_name)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        
    def get_driver_color(self, driver_name):
        """Get color for a driver based on name"""
        # Check by driver name first
        if driver_name in self.driver_colors:
            division_name = self.driver_colors[driver_name]
            return self.available_colors.get(division_name, self.available_colors["Default"])
 
        return self.available_colors["Default"]
        
    def load_different_config(self):
        """Load a different color configuration file"""
        self.focus_bindings(False)
        from tkinter import filedialog
    
        file_path = filedialog.askopenfilename(
            title="Select Divison Color Config File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir="."
        )
    
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self.driver_colors = json.load(f)
                self.color_config_file = file_path
                self.save_settings()  # Save the new config file path
                # Show brief confirmation
                original_text = self.load_config_btn['text']
                self.load_config_btn.config(text="✓", bg='#4CAF50')
                self.root.after(1000, lambda: self.load_config_btn.config(text=original_text, bg='#555555'))
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load config file: {e}")
        self.focus_bindings(True)
        
    def telemetry_loop(self):
        """Main telemetry loop"""
        while self.running:
            try:
                if not self.is_connected:
                    if self.ir.startup():
                        self.is_connected = True
                        
                if self.is_connected:
                    if self.ir.is_connected and self.ir.is_initialized:
                        self.process_telemetry()
                    else:
                        self.is_connected = False
                        self.ir.shutdown()
                        
                time.sleep(0.1)  # Update every 100ms
                
            except Exception as e:
                print(f"Telemetry error: {e}")
                time.sleep(1)
                
    def calculate_real_time_positions(self, drivers, live_data, player_car_class_id):
        """Calculate real-time positions based on track position and lap count"""
        car_idx_lap = live_data['CarIdxLap']
        car_idx_lap_dist_pct = live_data['CarIdxLapDistPct']
        car_idx_class_position = live_data['CarIdxClassPosition']
    
        if not car_idx_lap or not car_idx_lap_dist_pct or not car_idx_class_position:
            return []
    
        # Collect all active drivers with their track position data
        active_drivers = []
    
        for car_idx in range(len(car_idx_class_position)):
            if car_idx_class_position[car_idx] == 0:  # Not in race
                continue
            
            # Find driver info
            driver_info = None
            for driver in drivers:
                if driver.get('CarIdx') == car_idx:
                    driver_info = driver
                    break
                
            if not driver_info:
                continue
            
            # Filter by class if player is on track
            if player_car_class_id is not None:
                if driver_info.get('CarClassID') != player_car_class_id:
                    continue
        
            # Calculate total track position (lap + percentage through current lap)
            current_lap = car_idx_lap[car_idx]
            lap_pct = car_idx_lap_dist_pct[car_idx]
        
            # Handle invalid lap percentage data
            if lap_pct < 0 or lap_pct > 1:
                lap_pct = 0
            
            total_track_position = current_lap + lap_pct
        
            active_drivers.append({
                'car_idx': car_idx,
                'driver_info': driver_info,
                'total_track_position': total_track_position,
                'current_lap': current_lap,
                'lap_pct': lap_pct,
                'official_position': car_idx_class_position[car_idx]
            })
    
        # Sort by total track position (descending - highest lap + percentage first)
        active_drivers.sort(key=lambda x: x['total_track_position'], reverse=True)
    
        # Assign real-time positions
        for i, driver in enumerate(active_drivers):
            driver['real_time_position'] = i + 1
    
        return active_drivers

    def get_official_positions(self, drivers, live_data, player_car_class_id):
        """Get official positions for practice/qualifying sessions"""
        car_idx_class_position = live_data['CarIdxClassPosition']
    
        if not car_idx_class_position:
            return []
    
        active_drivers = []
    
        for car_idx in range(len(car_idx_class_position)):
            if car_idx_class_position[car_idx] == 0:  # Not in race
                continue
            
            # Find driver info
            driver_info = None
            for driver in drivers:
                if driver.get('CarIdx') == car_idx:
                    driver_info = driver
                    break
                
            if not driver_info:
                continue
            
            # Filter by class if player is on track
            if player_car_class_id is not None:
                if driver_info.get('CarClassID') != player_car_class_id:
                    continue
        
            active_drivers.append({
                'car_idx': car_idx,
                'driver_info': driver_info,
                'official_position': car_idx_class_position[car_idx]
            })
    
        # Sort by official position
        active_drivers.sort(key=lambda x: x['official_position'])
    
        return active_drivers

    def process_telemetry(self):
        """Process telemetry data with conditional real-time position calculations and simplified disconnect handling"""
        try:
            # Get driver info directly from telemetry
            try:
                drivers = self.ir['DriverInfo']['Drivers']
                if not drivers:
                    return
            except (KeyError, TypeError) as e:
                print(f"Error getting driver info: {e}")
                return
            
            # Get session type
            try:
                session_info = self.ir['SessionInfo']
                current_session = session_info['Sessions'][self.ir['SessionNum']]
                session_type = current_session['SessionType']
                is_race = session_type.lower() == 'race'
            except (KeyError, TypeError, IndexError):
                is_race = False
        
            # Get player car index and class
            try:
                self.player_car_idx = self.ir['PlayerCarIdx']
            except (KeyError, TypeError):
                self.player_car_idx = None

            player_car_class_id = None
            if self.player_car_idx is not None:
                try:
                    for driver in drivers:
                        if driver.get('CarIdx') == self.player_car_idx:
                            player_car_class_id = driver.get('CarClassID')
                            break
                except (KeyError, TypeError):
                    pass
        
            # Get live telemetry
            live_data = self.ir
            if not live_data:
                return
        
            # Use different methods based on session type
            if is_race:
                # Use real-time positions for races
                active_drivers = self.calculate_real_time_positions(drivers, live_data, player_car_class_id)
                position_key = 'real_time_position'
            else:
                # Use official positions for practice/qualifying
                active_drivers = self.get_official_positions(drivers, live_data, player_car_class_id)
                position_key = 'official_position'
        
            if not active_drivers:
                return
            
            # Get timing data for gap calculations (always use official method)
            car_idx_lap = live_data['CarIdxLap']
            car_idx_est_time = live_data['CarIdxEstTime']
            car_idx_lap_dist_pct = live_data['CarIdxLapDistPct']
        
            # Calculate division positions using the appropriate position type
            all_drivers_with_colors = []
            for driver in active_drivers:
                driver_color = self.get_driver_color(driver['driver_info'].get('UserName', ''))
                all_drivers_with_colors.append({
                    'car_idx': driver['car_idx'],
                    'position': driver[position_key],
                    'color': driver_color,
                    'official_position': driver.get('official_position', driver[position_key])
                })

            # Calculate division positions using display positions
            division_positions = {}
            for color in set(d['color'] for d in all_drivers_with_colors):
                same_color = [d for d in all_drivers_with_colors if d['color'] == color]
                same_color.sort(key=lambda x: x['position'])
                for i, driver in enumerate(same_color):
                    division_positions[driver['car_idx']] = i + 1
        
            # Process race standings
            self.race_data = []
        
            for driver in active_drivers:
                car_idx = driver['car_idx']
                driver_info = driver['driver_info']
            
                # Use the appropriate position for display
                position = driver[position_key]
            
                # Get current driver's color and division position
                current_driver_color = self.get_driver_color(driver_info.get('UserName', ''))
                current_color_position = division_positions.get(car_idx, position)

                # Calculate gap - check for disconnected drivers
                if current_color_position == 1:
                    gap = "Leader"
                elif is_race:
                    # Check if current driver is disconnected
                    if not car_idx_est_time or car_idx >= len(car_idx_est_time) or car_idx_est_time[car_idx] <= 0:
                        gap = "D/C"
                    else:
                        # Find division drivers using display positions
                        same_color_drivers = []
                        for temp_driver in active_drivers:
                            temp_color = self.get_driver_color(temp_driver['driver_info'].get('UserName', ''))
                            if temp_color == current_driver_color:
                                same_color_drivers.append({
                                    'car_idx': temp_driver['car_idx'],
                                    'position': temp_driver[position_key]
                                })
                    
                        same_color_drivers.sort(key=lambda x: x['position'])
                    
                        # Find current driver's position in the list
                        current_pos_index = None
                        for i, temp_driver in enumerate(same_color_drivers):
                            if temp_driver['car_idx'] == car_idx:
                                current_pos_index = i
                                break
                    
                        if current_pos_index is not None and current_pos_index > 0:
                            # Get car ahead in division
                            car_ahead_idx = same_color_drivers[current_pos_index - 1]['car_idx']
                        
                            # Check if car ahead is disconnected
                            if (not car_idx_est_time or car_ahead_idx >= len(car_idx_est_time) or 
                                car_idx_est_time[car_ahead_idx] <= 0):
                                # Car ahead is disconnected, leave gap blank
                                gap = ""
                            else:
                                # Both cars connected, calculate gap normally
                                current_est_time = car_idx_est_time[car_idx]
                                ahead_est_time = car_idx_est_time[car_ahead_idx]
                                current_lap = car_idx_lap[car_idx]
                                ahead_lap = car_idx_lap[car_ahead_idx]
            
                                time_gap = 0.0
                                if current_est_time > 0 and ahead_est_time > 0:
                                    time_gap = ahead_est_time - current_est_time
                                else:
                                    # Fallback to distance calculation
                                    time_gap = (car_idx_lap_dist_pct[car_ahead_idx] - car_idx_lap_dist_pct[car_idx]) * self.get_fastest_lap_time(current_session)
                
                                # Adjust for lap differences
                                lap_difference = ahead_lap - current_lap
                                
                                # If less than 1 FULL lap down
                                if lap_difference == 1 and car_idx_lap_dist_pct[car_ahead_idx] < car_idx_lap_dist_pct[car_idx]:
                                    time_gap += self.get_fastest_lap_time(current_session)
                                    lap_difference = 0

                                if lap_difference > 0:
                                    gap = f"{lap_difference}L"
                                else:
                                    if time_gap < 0:
                                        time_gap *= -1 # just make it positive for now
                                    if time_gap < 60:
                                        gap = f"{time_gap:.1f}"
                                    else:
                                        minutes = int(time_gap // 60)
                                        seconds = time_gap % 60
                                        gap = f"{minutes}:{seconds:04.1f}"
                        else:
                            gap = ""
                else:  # Practice or Qualifying
                    same_color_drivers = [d for d in all_drivers_with_colors if d['color'] == current_driver_color]
                    same_color_drivers.sort(key=lambda x: x['position'])

                    if len(same_color_drivers) >= current_color_position - 1:
                        car_ahead_idx = same_color_drivers[current_color_position - 2]['car_idx']
                        current_best = self.get_best_lap_from_session_info(current_session, car_idx)
                        ahead_best = self.get_best_lap_from_session_info(current_session, car_ahead_idx)
                        if current_best > 0 and ahead_best > 0:
                            time_gap = current_best - ahead_best
                            gap = f"{time_gap:.3f}"
                        else:
                            gap = ""
                    else:
                        gap = ""
            
                # Mark if this is the player
                is_player = (car_idx == self.player_car_idx)
            
                self.race_data.append({
                    'position': position,
                    'division_position': current_color_position,
                    'car_number': driver_info.get('CarNumber', ''),
                    'driver_name': driver_info.get('UserName', ''),
                    'gap': gap,
                    'car_idx': car_idx,
                    'is_player': is_player
                })
        
            # Sort by display position
            self.race_data.sort(key=lambda x: x['position'])
    
        except Exception as e:
            print(f"Processing error: {e}")

    def get_fastest_lap_time(self, current_session):
        fastest_time = float('inf')
        for driver in current_session['ResultsPositions']:
            best_lap = driver['FastestTime']
            if 0 < best_lap < fastest_time:
                fastest_time = best_lap
        return fastest_time if fastest_time != float('inf') else 90

    def get_best_lap_from_session_info(self, current_session, car_idx):
        try:
            if 'ResultsPositions' in current_session:
                for driver in current_session['ResultsPositions']:
                    if driver.get('CarIdx') == car_idx and 'FastestTime' in driver:
                        return driver['FastestTime']
        except (KeyError, TypeError, IndexError):
            pass
        return 90 # default to 90 if no best lap found
            
    def update_gui(self):
        """Update GUI with race data"""
        while self.running:
            try:
                if self.is_connected:
                    # Get session type for status display
                    try:
                        session_info = self.ir['SessionInfo']
                        current_session = session_info['Sessions'][self.ir['SessionNum']]
                        session_type = current_session['SessionType']
                        status_text = f"Connected - Live Data ({session_type})"
                    except (KeyError, TypeError, IndexError, AttributeError):
                        status_text = "Connected - Live Data"

                    self.root.after(0, lambda text=status_text: self.status_label.config(text=text, fg='green'))
                    self.root.after(0, self.display_race_data)
                else:
                    # Cancel hide timer if disconnected
                    if self.status_hide_timer:
                        self.root.after_cancel(self.status_hide_timer)
                        self.status_hide_timer = None
                    self.root.after(0, lambda: self.status_label.pack(pady=5))
                    self.root.after(0, lambda: self.status_label.config(text="Connecting to iRacing...", fg='yellow'))
                    
                time.sleep(0.1)  # Update GUI every 100ms
                
            except Exception as e:
                print(f"GUI update error: {e}")
                time.sleep(1)
    
    def get_dynamic_column_sizes(self, is_header=False):
        """Calculate column minimum sizes based on current window width"""
        # Account for scrollbar and padding
        scrollbar_width = 0 if not is_header else 4
        padding = 2  # Total padding from margins
        available_width = self.root.winfo_width() - scrollbar_width - padding
        
        # Define percentage allocations (should add up to 1.0)
        percentages = {
            'pos': 0.11,
            'class_pos': 0.11,
            'car_num': 0.13,
            'driver': 0.46,
            'gap': 0.19
        }
        
        # Calculate actual pixel widths
        return {
            'pos': int(available_width * percentages['pos']),
            'class_pos': int(available_width * percentages['class_pos']),
            'car_num': int(available_width * percentages['car_num']),
            'driver': int(available_width * percentages['driver']),
            'gap': int(available_width * percentages['gap'])
        }
                
    def display_race_data(self):
        """Display race data in the GUI - optimized to prevent flicker"""
        if not self.race_data:
            return
            
        # Replace the existing filter section with:
        if self.show_only_my_division and self.player_car_idx is not None:
            # Find player's color
            player_color = None
            for driver_data in self.race_data:
                if driver_data['car_idx'] == self.player_car_idx:
                    player_color = self.get_driver_color(driver_data['driver_name'])
                    break
                
            if player_color:
                current_data = [d for d in self.race_data if self.get_driver_color(d['driver_name']) == player_color]
            else:
                current_data = self.race_data
        elif self.current_division_filter is not None:
            # Filter by specific division
            division_color = self.available_colors.get(self.current_division_filter)
            if division_color:
                current_data = [d for d in self.race_data if self.get_driver_color(d['driver_name']) == division_color]
            else:
                current_data = self.race_data
        else:
            current_data = self.race_data
        
        # Check if we need to rebuild the display
        need_rebuild = (len(current_data) != len(self.displayed_data) or
                       any(d1['car_idx'] != d2['car_idx'] for d1, d2 in zip(current_data, self.displayed_data)))
        
        if need_rebuild:
            self.rebuild_display(current_data)
        else:
            self.update_existing_display(current_data)
            
        # Auto-center on player if enough time has passed since manual scroll
        if (self.player_car_idx is not None and 
            time.time() - self.last_manual_scroll > self.manual_scroll_timeout):
            self.center_on_player(current_data)

        self.displayed_data = current_data.copy()
        
    def center_on_player(self, current_data):
        """Center the view on the player's position"""
        if not current_data or self.player_car_idx is None:
            return
            
        # Find player's position in the data
        player_index = None
        for i, driver_data in enumerate(current_data):
            if driver_data['car_idx'] == self.player_car_idx:
                player_index = i
                break
                
        if player_index is None:
            return
            
        # Wait a frame to ensure canvas is properly updated
        self.root.after(1, lambda: self._do_center_scroll(current_data))
    
    def _do_center_scroll(self, current_data):
        """Actually perform the centering scroll"""
        try:
            # Force canvas update
            self.canvas.update_idletasks()
        
            if not current_data:
                return
            
            # Find the player's index in the active drivers list
            player_active_index = None
            for i, driver_data in enumerate(current_data):
                if driver_data['car_idx'] == self.player_car_idx:
                    player_active_index = i
                    break
                
            if player_active_index is None:
                return
            
            # Get canvas and content dimensions
            canvas_height = self.canvas.winfo_height()
            bbox = self.canvas.bbox("all")
            if not bbox:
                return
                
            total_height = bbox[3] - bbox[1]
        
            # If everything fits in the canvas, just scroll to top
            if total_height <= canvas_height:
                self.canvas.yview_moveto(0)
                return
        
            # Calculate how many items are visible at once
            item_height = total_height / len(current_data)
            visible_items = canvas_height / item_height

            # Calculate the ideal scroll position to center the player
            # We want the player to be in the middle of the visible area
            center_position = player_active_index - (visible_items / 2)

            # Convert to a fraction (0.0 to 1.0)
            max_scroll_position = len(current_data)
            if max_scroll_position <= 0:
                scroll_fraction = 0.0
            else:
                scroll_fraction = center_position / max_scroll_position
                scroll_fraction = max(0.0, min(1.0, scroll_fraction))

            # Apply the scroll
            self.canvas.yview_moveto(0.0)
            self.canvas.yview_moveto(scroll_fraction)
        
        except Exception as e:
            print(f"Error centering on player: {e}")

    def on_window_resize(self, event):
        """Handle window resize events"""
        if event.widget == self.root:
            # Recreate headers with new widths
            self.root.after(100, self.refresh_layout)  # Small delay to avoid excessive calls
            
            # Save position after resize (existing functionality)
            self.root.after(1000, self.save_settings)

    def refresh_layout(self):
        """Refresh the layout after window resize"""
        # Recreate headers
        self.create_headers()
    
        # Force a display refresh to update row widths
        if hasattr(self, 'displayed_data') and self.displayed_data:
            self.rebuild_display(self.displayed_data)
        
    def rebuild_display(self, data):
        """Rebuild the entire display"""
        # Clear existing data widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
            
        self.data_widgets = {}
        
        # Create new widgets
        for i, driver_data in enumerate(data):
            self.create_driver_row(i, driver_data)
            
    def create_driver_row(self, index, data):
        """Create a new driver row using grid layout"""
        row_frame = tk.Frame(self.scrollable_frame, bg='black')
        row_frame.pack(fill=tk.X, expand=True, padx=5, pady=1)
    
        sizes = self.get_dynamic_column_sizes()

        # Configure same grid with dynamic sizes and uniform groups
        row_frame.grid_columnconfigure(0, weight=sizes['pos'], minsize=sizes['pos'], uniform="col0")
        row_frame.grid_columnconfigure(1, weight=sizes['class_pos'], minsize=sizes['class_pos'], uniform="col1")
        row_frame.grid_columnconfigure(2, weight=sizes['car_num'], minsize=sizes['car_num'], uniform="col2")
        row_frame.grid_columnconfigure(3, weight=sizes['driver'], minsize=sizes['driver'], uniform="col3")
        row_frame.grid_columnconfigure(4, weight=sizes['gap'], minsize=sizes['gap'], uniform="col4")
    
        # Get driver color
        color = self.get_driver_color(data['driver_name'])
    
        # Highlight player row
        if data['is_player']:
            row_frame.configure(bg='#1a1a1a')
    
        # Create labels using grid instead of pack
        pos_label = tk.Label(row_frame, text=str(data['position']), 
                        fg=color, bg=row_frame['bg'], 
                        font=('Arial', 9, 'bold' if data['is_player'] else 'normal'))
        pos_label.grid(row=0, column=0, sticky='ew', padx=2)

        division_pos_label = tk.Label(row_frame, text=str(data['division_position']), 
                        fg=color, bg=row_frame['bg'], 
                        font=('Arial', 9, 'bold' if data['is_player'] else 'normal'))
        division_pos_label.grid(row=0, column=1, sticky='ew', padx=2)
    
        car_label = tk.Label(row_frame, text=data['car_number'], 
                        fg=color, bg=row_frame['bg'], 
                        font=('Arial', 9, 'bold' if data['is_player'] else 'normal'))
        car_label.grid(row=0, column=2, sticky='ew', padx=2)

        name_anchor = "w" # Left align name
        if self.center_drivers:
            name_anchor = "center" # Center name
        name_label = tk.Label(row_frame, text=data['driver_name'], 
                    fg=color, bg=row_frame['bg'], 
                    font=('Arial', 9, 'bold' if data['is_player'] else 'normal'),
                    anchor=name_anchor, width=sizes['driver'])  
        name_label.grid(row=0, column=3, sticky='ew', padx=2)
    
        gap_label = tk.Label(row_frame, text=data['gap'], 
                        fg='white', bg=row_frame['bg'], 
                        font=('Arial', 9, 'bold' if data['is_player'] else 'normal'), 
                        anchor="w")
        gap_label.grid(row=0, column=4, sticky='', padx=2)
        
        # Bind right-click to row frame and all labels for context menu
        row_frame.bind("<Button-3>", lambda e: self.show_context_menu(e, data['driver_name']))
        pos_label.bind("<Button-3>", lambda e: self.show_context_menu(e, data['driver_name']))
        division_pos_label.bind("<Button-3>", lambda e: self.show_context_menu(e, data['driver_name']))
        car_label.bind("<Button-3>", lambda e: self.show_context_menu(e, data['driver_name']))
        name_label.bind("<Button-3>", lambda e: self.show_context_menu(e, data['driver_name']))
        gap_label.bind("<Button-3>", lambda e: self.show_context_menu(e, data['driver_name']))
        
        # Store widget references
        self.data_widgets[data['car_idx']] = {
            'frame': row_frame,
            'position': pos_label,
            'division_position': division_pos_label,
            'car_number': car_label,
            'name': name_label,
            'gap': gap_label
        } 
        
    def update_existing_display(self, data):
        """Update existing widgets with new data"""
        for i, driver_data in enumerate(data):
            car_idx = driver_data['car_idx']
            if car_idx in self.data_widgets:
                widgets = self.data_widgets[car_idx]
                
                # Get driver color
                color = self.get_driver_color(driver_data['driver_name'])
                
                # Update row background for player
                bg_color = '#1a1a1a' if driver_data['is_player'] else 'black'
                widgets['frame'].configure(bg=bg_color)
                
                # Update font weight for player
                font_weight = 'bold' if driver_data['is_player'] else 'normal'
                
                # Update only if values changed
                if widgets['position']['text'] != str(driver_data['position']):
                    widgets['position'].config(text=str(driver_data['position']), fg=color, bg=bg_color,
                                            font=('Arial', 9, font_weight))

                if widgets['division_position']['text'] != str(driver_data['division_position']):
                    widgets['division_position'].config(text=str(driver_data['division_position']), fg=color, bg=bg_color,
                                            font=('Arial', 9, font_weight))
                    
                if widgets['car_number']['text'] != driver_data['car_number']:
                    widgets['car_number'].config(text=driver_data['car_number'], fg=color, bg=bg_color,
                                            font=('Arial', 9, font_weight))
                
                if widgets['name']['text'] != driver_data['driver_name']:
                    widgets['name'].config(text=driver_data['driver_name'], fg=color, bg=bg_color,
                                            font=('Arial', 9, font_weight))
                    
                if widgets['gap']['text'] != driver_data['gap']:
                    widgets['gap'].config(text=driver_data['gap'], bg=bg_color,
                                         font=('Arial', 9, font_weight))
                                                  
    def reorder_and_update_display(self, data):
        """Reorder existing widgets and update their data without rebuilding"""
        # Temporarily disable canvas updates
        self.scrollable_frame.update_idletasks()
    
        # Get all current widget frames
        existing_frames = []
        for driver_data in data:
            car_idx = driver_data['car_idx']
            if car_idx in self.data_widgets:
                existing_frames.append(self.data_widgets[car_idx]['frame'])
    
        # Repack frames in correct order
        for i, frame in enumerate(existing_frames):
            frame.pack_forget()
    
        for i, driver_data in enumerate(data):
            car_idx = driver_data['car_idx']
            if car_idx in self.data_widgets:
                widgets = self.data_widgets[car_idx]
                frame = widgets['frame']
            
                # Repack in correct position
                frame.pack(fill=tk.X, padx=5, pady=1)
            
                # Update data
                color = self.get_driver_color(driver_data['driver_name'])
                bg_color = '#1a1a1a' if driver_data['is_player'] else 'black'
                font_weight = 'bold' if driver_data['is_player'] else 'normal'
            
                # Update frame background
                frame.configure(bg=bg_color)
            
                # Update all widgets at once
                widgets['position'].config(text=str(driver_data['position']), fg=color, bg=bg_color,
                                    font=('Arial', 9, font_weight))
                widgets['division_position'].config(text=str(driver_data['division_position']), fg=color, bg=bg_color,
                                    font=('Arial', 9, font_weight))
                widgets['car_number'].config(text=driver_data['car_number'], fg=color, bg=bg_color,
                                    font=('Arial', 9, font_weight))
                widgets['name'].config(text=driver_data['driver_name'], fg=color, bg=bg_color,
                                    font=('Arial', 9, font_weight))
                widgets['gap'].config(text=driver_data['gap'], fg='white', bg=bg_color,
                                    font=('Arial', 9, font_weight))                 
                            
    def run(self):
        """Run the application"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            if self.is_connected:
                self.ir.shutdown()

if __name__ == "__main__":
    try:
        app = leagueOverlay()
        app.run()
    except Exception as e:
        import traceback
        with open('error_log.txt', 'w') as f:
            f.write(f"Error: {e}\n")
            f.write(traceback.format_exc())
        # Show error dialog if possible
        try:
            import tkinter.messagebox as msgbox
            msgbox.showerror("Error", f"An error occurred: {e}")
        except:
            pass