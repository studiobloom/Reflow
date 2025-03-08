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
        
        # Create tooltip label
        label = tk.Label(
            self.tooltip,
            text=self.text,
            justify=tk.LEFT,
            background="#2b2b2b",
            foreground="#ffffff",
            relief=tk.SOLID,
            borderwidth=1,
            font=("Segoe UI", 9)
        )
        label.pack()

    def leave(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

class ReflowGUI:
    def __init__(self):
        """Initialize the GUI"""
        self.root = ctk.CTk()
        self.root.title("Reflow - Webflow Site Exporter")
        self.root.geometry("800x700")
        self.root.minsize(800, 700)
        
        # Configure the appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Configure fonts
        self.header_font = ("Segoe UI", 13, "bold")
        self.label_font = ("Segoe UI", 11)
        self.button_font = ("Segoe UI", 11)
        self.small_font = ("Segoe UI", 10)
        
        # URL Input Frame
        url_frame = ctk.CTkFrame(self.root, corner_radius=0)
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
        settings_frame = ctk.CTkFrame(self.root, corner_radius=0)
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
            corner_radius=0
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
        
        self.cms_var = tk.BooleanVar(value=True)
        cms_check = ctk.CTkCheckBox(
            options_frame,
            text="Process CMS Collections",
            variable=self.cms_var,
            font=self.label_font,
            border_width=1,
            corner_radius=0,
            hover_color="#1f6aaa"
        )
        cms_check.pack(side=tk.LEFT, padx=10, pady=2)
        ToolTip(cms_check, "Enable to process and download CMS collection pages\nRequired if your site uses dynamic collections")
        
        self.css_var = tk.BooleanVar(value=False)
        css_check = ctk.CTkCheckBox(
            options_frame,
            text="Retain Original Asset URLs",
            variable=self.css_var,
            font=self.label_font,
            border_width=1,
            corner_radius=0,
            hover_color="#1f6aaa"
        )
        css_check.pack(side=tk.LEFT, padx=10, pady=2)
        ToolTip(css_check, "Keep original URLs for assets in CSS files\nEnable if you want assets to load from Webflow servers")
        
        self.zip_var = tk.BooleanVar(value=True)
        zip_check = ctk.CTkCheckBox(
            options_frame,
            text="Create ZIP Archive",
            variable=self.zip_var,
            command=self.toggle_zip_mode,
            font=self.label_font,
            border_width=1,
            corner_radius=0,
            hover_color="#1f6aaa"
        )
        zip_check.pack(side=tk.LEFT, padx=10, pady=2)
        ToolTip(zip_check, "Create a ZIP file containing the exported site\nRecommended for easier file handling")
        
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
            border_width=1
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
            border_width=1
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
            self.root,
            text="Export Site",
            command=self.start_export,
            height=32,
            font=("Segoe UI", 12, "bold"),
            corner_radius=0,
            border_width=0,
            fg_color="#1f6aaa",
            hover_color="#1c5c94"
        )
        self.export_button.pack(pady=(5, 15), padx=15)
        
        # Preview/Log Area
        preview_label_frame = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0)
        preview_label_frame.pack(fill=tk.X, padx=15, pady=(0, 5))
        
        self.preview_label = ctk.CTkLabel(
            preview_label_frame,
            text="Export Progress:",
            font=self.header_font
        )
        self.preview_label.pack(anchor=tk.W)
        
        self.preview_frame = ctk.CTkFrame(self.root, corner_radius=0)
        self.preview_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))
        
        self.preview_text = scrolledtext.ScrolledText(
            self.preview_frame,
            wrap=tk.WORD,
            height=10,
            bg='#1a1a1a',
            fg='#e6e6e6',
            font=("Consolas", 10),
            border=0
        )
        self.preview_text.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        
        # Status bar
        status_frame = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0, height=25)
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
        if self.zip_var.get():
            filename = filedialog.asksaveasfilename(
                title="Save Export As",
                defaultextension=".zip",
                filetypes=[("ZIP archives", "*.zip"), ("All files", "*.*")],
                initialfile="webflow_export.zip"
            )
        else:
            filename = filedialog.askdirectory(
                title="Select Export Location",
                initialdir=os.path.abspath(self.output_entry.get())
            )
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
            self.preview_text.insert(tk.END, "Error: Please select an export location\n")
            return
            
        # Clear preview area
        self.preview_text.delete(1.0, tk.END)
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
                log_level=logging.INFO  # Always use normal logging
            )
            
            # Start the export
            exporter.crawl_site()
            
            self.preview_text.insert(tk.END, "\nExport completed successfully!\n")
            
            # Print summary
            self.preview_text.insert(tk.END, "\nExport Summary:\n")
            self.preview_text.insert(tk.END, f"- Pages downloaded: {len(exporter.visited_urls)}\n")
            self.preview_text.insert(tk.END, f"- Assets downloaded: {len(exporter.assets_to_download)}\n")
            if hasattr(exporter, 'cms_pages'):
                self.preview_text.insert(tk.END, f"- CMS collections detected: {len(exporter.cms_pages)}\n")
            
        except Exception as e:
            self.preview_text.insert(tk.END, f"Error during export: {str(e)}\n")
        finally:
            self.status_label.configure(text="Ready")
            self.export_button.configure(state="normal")
            
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = ReflowGUI()
    app.run() 