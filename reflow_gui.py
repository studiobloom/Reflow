import tkinter as tk
import customtkinter as ctk
from tkinter import scrolledtext, filedialog
import threading
import webbrowser
from urllib.parse import urlparse
import os
import sys
import logging
from reflow import Reflow
from tkinter import ttk

# Color constants
PRIMARY_COLOR = "#6189ff"  # Main blue color
PRIMARY_HOVER = "#4f6ecc"  # Darker blue for hover states (20% darker)

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_path, relative_path)

class ToolTip(object):
    """Create a tooltip for a given widget"""
    def __init__(self, widget, text=''):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind('<Enter>', self.enter)
        self.widget.bind('<Leave>', self.leave)

    def enter(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        # Create top level window
        self.tooltip = tk.Toplevel(self.widget)
        # Remove window decorations
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        
        # Try to set icon for tooltip window
        try:
            # Get icon path from parent window if available
            parent = self.widget.winfo_toplevel()
            if hasattr(parent, 'get_icon_path') and callable(parent.get_icon_path):
                icon_path = parent.get_icon_path()
            else:
                icon_path = get_resource_path("reflow.ico")
            self.tooltip.iconbitmap(icon_path)
        except:
            # Ignore errors as tooltip windows may not support icons in all cases
            pass
        
        # Create tooltip label
        label = tk.Label(
            self.tooltip,
            text=self.text,
            justify=tk.LEFT,
            background="#2b2b2b",
            foreground="#ffffff",
            relief=tk.SOLID,
            borderwidth=0,
            font=("Segoe UI", 9)
        )
        label.pack()

    def leave(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

class ReflowGUI(ctk.CTk):
    def __init__(self):
        """Initialize the GUI"""
        super().__init__()
        
        # Set up logging handler for GUI
        class TextHandler(logging.Handler):
            def __init__(self, text_widget):
                super().__init__()
                self.text_widget = text_widget
                
            def emit(self, record):
                msg = self.format(record)
                self.text_widget.insert(tk.END, msg + '\n')
                self.text_widget.see(tk.END)  # Auto-scroll to the bottom
                
                # Process any pending events to update the GUI
                self.text_widget.update_idletasks()
        
        # Store the TextHandler class for later use
        self.TextHandler = TextHandler
        
        self.title("Reflow - Webflow Site Exporter")
        self.geometry("800x700")
        self.minsize(800, 700)
        
        # Set the application icon for all windows
        self.icon_path = get_resource_path("reflow.ico")
        try:
            if os.path.exists(self.icon_path):
                self.iconbitmap(self.icon_path)
                # Set icon for all future toplevel windows
                self.tk.call('wm', 'iconbitmap', self._w, self.icon_path)
        except Exception as e:
            print(f"Failed to set icon: {str(e)}")  # Add debug print
            pass  # Ignore if icon setting fails
        
        # Configure the appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Configure fonts
        self.header_font = ("Segoe UI", 13, "bold")
        self.label_font = ("Segoe UI", 11)
        self.button_font = ("Segoe UI", 11)
        self.small_font = ("Segoe UI", 10)
        
        # URL Input Frame
        url_frame = ctk.CTkFrame(self, corner_radius=0)
        url_frame.pack(fill=tk.X, padx=15, pady=(15, 10))
        
        url_label = ctk.CTkLabel(
            url_frame,
            text="Webflow URL:",
            font=self.label_font
        )
        url_label.pack(side=tk.LEFT, padx=(10, 5))
        
        self.url_entry = ctk.CTkEntry(
            url_frame,
            placeholder_text="https://your-site.webflow.io",
            width=300,
            height=28,
            border_width=1,
            corner_radius=0
        )
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=8)
        
        # Add tooltip for URL entry
        ToolTip(self.url_entry, "Enter the URL of your Webflow site\nExample: https://your-site.webflow.io")
        
        # Settings frame
        settings_frame = ctk.CTkFrame(self, corner_radius=0)
        settings_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        # Output Directory
        output_section = ctk.CTkFrame(settings_frame, fg_color=("gray85", "gray17"), corner_radius=0)
        output_section.pack(fill=tk.X, padx=8, pady=8)
        
        output_label = ctk.CTkLabel(
            output_section,
            text="Export Location",
            font=self.header_font
        )
        output_label.pack(anchor=tk.W, padx=10, pady=(8, 5))
        
        output_subframe = ctk.CTkFrame(output_section, fg_color="transparent", corner_radius=0)
        output_subframe.pack(fill=tk.X, padx=10, pady=(0, 8))
        
        self.output_entry = ctk.CTkEntry(
            output_subframe,
            placeholder_text="Select location...",
            height=28,
            border_width=1,
            corner_radius=0
        )
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Add tooltip for output entry
        ToolTip(self.output_entry, "Choose where to save the exported site\nWill be a ZIP file or folder depending on settings")

        browse_button = ctk.CTkButton(
            output_subframe,
            text="Browse",
            command=self.browse_output_directory,
            width=70,
            height=28,
            font=self.button_font,
            corner_radius=0,
            fg_color=PRIMARY_COLOR,
            hover_color=PRIMARY_HOVER
        )
        browse_button.pack(side=tk.LEFT)
        
        # Processing Options
        processing_section = ctk.CTkFrame(settings_frame, fg_color=("gray85", "gray17"), corner_radius=0)
        processing_section.pack(fill=tk.X, padx=8, pady=8)
        
        processing_label = ctk.CTkLabel(
            processing_section,
            text="Processing Options",
            font=self.header_font
        )
        processing_label.pack(anchor=tk.W, padx=10, pady=(8, 5))
        
        # Horizontal layout for processing options
        options_frame = ctk.CTkFrame(processing_section, fg_color="transparent", corner_radius=0)
        options_frame.pack(fill=tk.X, padx=10, pady=(0, 8))
        
        self.zip_var = tk.BooleanVar(value=True)
        zip_check = ctk.CTkSwitch(
            options_frame,
            text="Create ZIP Archive",
            variable=self.zip_var,
            command=self.toggle_zip_mode,
            font=self.label_font,
            button_color=PRIMARY_COLOR,
            button_hover_color=PRIMARY_HOVER,
            progress_color=PRIMARY_COLOR
        )
        zip_check.pack(side=tk.LEFT, padx=10, pady=2)
        ToolTip(zip_check, "Create a ZIP file containing the exported site\nRecommended for easier file handling")

        self.cms_var = tk.BooleanVar(value=True)
        cms_check = ctk.CTkSwitch(
            options_frame,
            text="Process CMS Collections",
            variable=self.cms_var,
            font=self.label_font,
            button_color=PRIMARY_COLOR,
            button_hover_color=PRIMARY_HOVER,
            progress_color=PRIMARY_COLOR
        )
        cms_check.pack(side=tk.LEFT, padx=10, pady=2)
        ToolTip(cms_check, "Enable to process and download CMS collection pages\nRequired if your site uses dynamic collections")
        
        self.css_var = tk.BooleanVar(value=False)
        css_check = ctk.CTkSwitch(
            options_frame,
            text="Retain Original Asset URLs",
            variable=self.css_var,
            font=self.label_font,
            button_color=PRIMARY_COLOR,
            button_hover_color=PRIMARY_HOVER,
            progress_color=PRIMARY_COLOR
        )
        css_check.pack(side=tk.LEFT, padx=10, pady=2)
        ToolTip(css_check, "Keep original URLs for assets in CSS files\nEnable if you want assets to load from Webflow servers")
        
        # Performance Settings
        perf_section = ctk.CTkFrame(settings_frame, fg_color=("gray85", "gray17"), corner_radius=0)
        perf_section.pack(fill=tk.X, padx=8, pady=8)
        
        perf_label = ctk.CTkLabel(
            perf_section,
            text="Performance Settings",
            font=self.header_font
        )
        perf_label.pack(anchor=tk.W, padx=10, pady=(8, 5))
        
        # Workers slider
        workers_frame = ctk.CTkFrame(perf_section, fg_color="transparent", corner_radius=0)
        workers_frame.pack(fill=tk.X, padx=10, pady=(0, 8))
        
        workers_label = ctk.CTkLabel(
            workers_frame,
            text="Max Workers:",
            font=self.label_font
        )
        workers_label.pack(side=tk.LEFT, padx=5)
        
        self.workers_value = tk.StringVar(value="5")
        self.workers_slider = ctk.CTkSlider(
            workers_frame,
            from_=5,
            to=20,
            number_of_steps=15,
            command=lambda v: self.workers_value.set(str(int(v))),
            width=200,
            height=16,
            corner_radius=0,
            border_width=1,
            progress_color=PRIMARY_COLOR,
            button_color=PRIMARY_COLOR,
            button_hover_color=PRIMARY_HOVER
        )
        self.workers_slider.pack(side=tk.LEFT, padx=10)
        self.workers_slider.set(5)
        ToolTip(self.workers_slider, "Number of concurrent downloads\nMore workers = faster export but higher server load\nDefault: 5, Max: 20")
        
        workers_value_label = ctk.CTkLabel(
            workers_frame,
            textvariable=self.workers_value,
            font=self.label_font
        )
        workers_value_label.pack(side=tk.LEFT)
        
        # Delay slider
        delay_frame = ctk.CTkFrame(perf_section, fg_color="transparent", corner_radius=0)
        delay_frame.pack(fill=tk.X, padx=10, pady=(0, 8))
        
        delay_label = ctk.CTkLabel(
            delay_frame,
            text="Request Delay (s):",
            font=self.label_font
        )
        delay_label.pack(side=tk.LEFT, padx=5)
        
        self.delay_value = tk.StringVar(value="0.2")
        self.delay_slider = ctk.CTkSlider(
            delay_frame,
            from_=0.2,
            to=2.0,
            number_of_steps=18,
            command=lambda v: self.delay_value.set(f"{v:.1f}"),
            width=200,
            height=16,
            corner_radius=0,
            border_width=1,
            progress_color=PRIMARY_COLOR,
            button_color=PRIMARY_COLOR,
            button_hover_color=PRIMARY_HOVER
        )
        self.delay_slider.pack(side=tk.LEFT, padx=10)
        self.delay_slider.set(0.2)
        ToolTip(self.delay_slider, "Delay between requests in seconds\nLonger delay = slower export but more polite\nDefault: 0.2s, Max: 2.0s")
        
        delay_value_label = ctk.CTkLabel(
            delay_frame,
            textvariable=self.delay_value,
            font=self.label_font
        )
        delay_value_label.pack(side=tk.LEFT)
        
        # Export button
        self.export_button = ctk.CTkButton(
            self,
            text="Export Site",
            command=self.start_export,
            height=32,
            font=("Segoe UI", 12, "bold"),
            corner_radius=0,
            border_width=0,
            fg_color=PRIMARY_COLOR,
            hover_color=PRIMARY_HOVER
        )
        self.export_button.pack(pady=(5, 10), padx=15)
        
        # Preview/Log Area
        self.preview_frame = ctk.CTkFrame(self, corner_radius=0)
        self.preview_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))
        
        # Header frame for label
        header_frame = ctk.CTkFrame(self.preview_frame, fg_color="transparent", corner_radius=0)
        header_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.preview_label = ctk.CTkLabel(
            header_frame,
            text="Export Progress:",
            font=self.header_font
        )
        self.preview_label.pack(side=tk.LEFT, padx=5)
        
        # Container for the log
        self.log_container = ctk.CTkFrame(self.preview_frame, fg_color="transparent", corner_radius=0)
        self.log_container.pack(fill=tk.BOTH, expand=True, padx=1, pady=(0, 1))
        
        # Create text widget and scrollbar
        self.preview_text = tk.Text(
            self.log_container,
            wrap=tk.WORD,
            height=10,
            bg='#1a1a1a',
            fg='#e6e6e6',
            font=("Consolas", 10),
            border=0,
            highlightthickness=0
        )
        self.preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # We'll set up the logging handler when needed, not at initialization
        self.text_handler = None
        
        # Create and configure CTkScrollbar
        scrollbar = ctk.CTkScrollbar(
            self.log_container,
            command=self.preview_text.yview,
            button_color="#404040",
            button_hover_color="#505050",
            fg_color="#2b2b2b"
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Connect textbox scroll event to CTk scrollbar
        self.preview_text.configure(yscrollcommand=scrollbar.set)
        
        # Status bar
        status_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0, height=25)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=15, pady=(0, 15))
        
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Ready",
            font=self.small_font,
            text_color="gray"
        )
        self.status_label.pack(side=tk.LEFT)
        
    def toggle_zip_mode(self):
        if self.zip_var.get():
            if not self.output_entry.get().endswith('.zip'):
                current = self.output_entry.get().rstrip('/')
                self.output_entry.delete(0, tk.END)
                self.output_entry.insert(0, current + '.zip')
        else:
            if self.output_entry.get().endswith('.zip'):
                current = self.output_entry.get()[:-4]
                self.output_entry.delete(0, tk.END)
                self.output_entry.insert(0, current)
    
    def browse_output_directory(self):
        # Set the parent window for the dialog to ensure icon inheritance
        parent = self
        
        # Get the URL to use for default filename
        url = self.url_entry.get().strip()
        default_filename = "webflow_export"
        
        if url:
            try:
                parsed_url = urlparse(url)
                if parsed_url.netloc:
                    domain = parsed_url.netloc
                    # Remove webflow.io if present
                    if domain.endswith('.webflow.io'):
                        domain = domain.replace('.webflow.io', '')
                    default_filename = domain
            except:
                pass  # Use default if parsing fails
        
        if self.zip_var.get():
            # Create a temporary toplevel to set the icon for the file dialog
            temp = tk.Toplevel(parent)
            temp.withdraw()  # Hide the temporary window
            temp.iconbitmap(self.icon_path)  # Set the icon
            
            filename = filedialog.asksaveasfilename(
                parent=temp,
                title="Save Export As",
                defaultextension=".zip",
                filetypes=[("ZIP archives", "*.zip"), ("All files", "*.*")],
                initialfile=f"{default_filename}.zip"
            )
            
            temp.destroy()  # Clean up the temporary window
        else:
            # Create a temporary toplevel to set the icon for the directory dialog
            temp = tk.Toplevel(parent)
            temp.withdraw()  # Hide the temporary window
            temp.iconbitmap(self.icon_path)  # Set the icon
            
            filename = filedialog.askdirectory(
                parent=temp,
                title="Select Export Location",
                initialdir=os.path.abspath(self.output_entry.get()) if self.output_entry.get() else os.getcwd()
            )
            
            temp.destroy()  # Clean up the temporary window
            
        if filename:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, filename)
        
    def start_export(self):
        url = self.url_entry.get().strip()
        if not url:
            self.preview_text.insert(tk.END, "Error: Please enter a valid Webflow URL\n")
            return
            
        try:
            parsed_url = urlparse(url)
            if not parsed_url.scheme or not parsed_url.netloc:
                raise ValueError("Invalid URL format")
        except ValueError:
            self.preview_text.insert(tk.END, "Error: Invalid URL format. Please include http:// or https://\n")
            return
            
        # Validate output directory
        output_dir = self.output_entry.get().strip()
        if not output_dir:
            # Auto-generate output name based on the site URL
            domain = parsed_url.netloc
            # Remove webflow.io if present
            if domain.endswith('.webflow.io'):
                domain = domain.replace('.webflow.io', '')
            
            # Set default output location
            if self.zip_var.get():
                output_dir = os.path.join(os.path.expanduser('~'), 'Downloads', f"{domain}.zip")
            else:
                output_dir = os.path.join(os.path.expanduser('~'), 'Downloads', domain)
            
            # Update the output entry
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, output_dir)
            
        # Clear preview area
        self.preview_text.delete(1.0, tk.END)
        
        # Set up logging to GUI for this export
        logger = logging.getLogger('reflow')
        
        # Remove any existing handlers
        for handler in logger.handlers[:]:
            if isinstance(handler, self.TextHandler):
                logger.removeHandler(handler)
        
        # Create and add new handler
        self.text_handler = self.TextHandler(self.preview_text)
        self.text_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(self.text_handler)
        
        self.preview_text.insert(tk.END, f"Starting export of {url}...\n")
        self.preview_text.insert(tk.END, f"Export location: {output_dir}\n")
        self.status_label.configure(text="Exporting...")
        self.export_button.configure(state="disabled")
        
        # Start export in a separate thread
        thread = threading.Thread(target=self.run_export, args=(url,))
        thread.daemon = True
        thread.start()
        
    def run_export(self, url):
        try:
            # Get settings from GUI
            output_dir = self.output_entry.get().strip()
            workers = int(float(self.workers_value.get()))
            delay = float(self.delay_value.get())
            
            # Create and run the exporter
            exporter = Reflow(
                url,
                output_dir,
                max_workers=workers,
                delay=delay,
                process_cms=self.cms_var.get(),
                process_css=self.css_var.get(),
                create_zip=self.zip_var.get(),
                log_level=logging.DEBUG,  # Set default to DEBUG for verbose logging
                log_file=None
            )
            
            # Start the export
            exporter.crawl_site()
            
            # Remove the logging handler
            logger = logging.getLogger('reflow')
            if self.text_handler in logger.handlers:
                logger.removeHandler(self.text_handler)
            
            # Add the summary directly to the text widget
            self.preview_text.insert(tk.END, "\n" + "-"*50 + "\n")
            self.preview_text.insert(tk.END, "Export completed successfully!\n\n")
            self.preview_text.insert(tk.END, "Export Summary:\n")
            self.preview_text.insert(tk.END, f"- Pages downloaded: {len(exporter.visited_urls)}\n")
            self.preview_text.insert(tk.END, f"- Assets downloaded: {len(exporter.assets_to_download)}\n")
            if hasattr(exporter, 'cms_pages'):
                self.preview_text.insert(tk.END, f"- CMS collections detected: {len(exporter.cms_pages)}\n")
            self.preview_text.insert(tk.END, f"\nExport saved to: {output_dir}\n")
            
            # Make sure to scroll to see the summary
            self.preview_text.see(tk.END)
            
        except Exception as e:
            # Remove the logging handler
            logger = logging.getLogger('reflow')
            if self.text_handler in logger.handlers:
                logger.removeHandler(self.text_handler)
                
            self.preview_text.insert(tk.END, "\n" + "-"*50 + "\n")
            self.preview_text.insert(tk.END, f"Error during export: {str(e)}\n")
            
            # Make sure to scroll to see the error
            self.preview_text.see(tk.END)
            
        finally:
            self.status_label.configure(text="Ready")
            self.export_button.configure(state="normal")
            
    def get_icon_path(self):
        """Helper method to get the icon path"""
        return self.icon_path
        
    def run(self):
        # Set icon for all dialogs
        self.createcommand('tk::dialog::file::ShowFileSelector', 
                               lambda *args: self.tk.call('tk::dialog::file::ShowFileSelector', *args))
        
        # Set default icon for all toplevel windows
        self.option_add('*Dialog.msg.font', self.label_font)
        self.option_add('*Dialog.msg.wrapLength', '6i')
        
        # Start the main loop
        self.mainloop()

if __name__ == "__main__":
    app = ReflowGUI()
    app.run() 