"""
Interactive Image Viewer and Quality Assessment Tool
- Browse downloaded imagery
- Rotate images to orient north
- Mark fiducial locations
- Accept/reject images
- Export QA results
"""

import os
import glob
import numpy as np
import pandas as pd
from pathlib import Path
import json
from PIL import Image
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from matplotlib.widgets import Button, Slider
from IPython.display import display, clear_output
import ipywidgets as widgets

# ============================================================================
# Configuration
# ============================================================================

IMAGE_DIR = '/content/edmonds_imagery'
QA_OUTPUT = '/content/drive/MyDrive/treedata/Full_Image/USGS/Image_QA_Results.csv'
FIDUCIAL_OUTPUT = '/content/drive/MyDrive/treedata/Full_Image/USGS/Fiducial_Marks.json'

# ============================================================================
# Image Viewer Class
# ============================================================================

class ImageViewer:
    def __init__(self, image_dir):
        self.image_dir = image_dir
        self.image_files = self.scan_images()
        self.current_idx = 0
        self.rotation = 0
        self.fiducials = []
        self.qa_results = []
        
        # Load existing QA results if available
        self.load_qa_results()
        
        # UI components
        self.fig = None
        self.ax = None
        self.img_display = None
        self.fiducial_circles = []
        
        print(f"Found {len(self.image_files)} images")
    
    def scan_images(self):
        """Find all TIFF images in directory"""
        pattern = os.path.join(self.image_dir, '**/*.tif')
        files = glob.glob(pattern, recursive=True)
        
        # Sort by year and filename
        files.sort()
        
        return files
    
    def load_qa_results(self):
        """Load existing QA results"""
        if os.path.exists(QA_OUTPUT):
            df = pd.read_csv(QA_OUTPUT)
            self.qa_results = df.to_dict('records')
            print(f"Loaded {len(self.qa_results)} existing QA records")
    
    def get_qa_for_image(self, filepath):
        """Get QA record for current image"""
        for record in self.qa_results:
            if record['Filepath'] == filepath:
                return record
        return None
    
    def save_qa_result(self, filepath, status, rotation, fiducials, notes=''):
        """Save QA result for image"""
        # Remove existing record
        self.qa_results = [r for r in self.qa_results if r['Filepath'] != filepath]
        
        # Add new record
        year = Path(filepath).parent.parent.name
        dataset = Path(filepath).parent.name
        filename = Path(filepath).name
        
        self.qa_results.append({
            'Filepath': filepath,
            'Year': year,
            'Dataset': dataset,
            'Filename': filename,
            'Status': status,
            'Rotation': rotation,
            'Num_Fiducials': len(fiducials),
            'Notes': notes
        })
        
        # Save to CSV
        df = pd.DataFrame(self.qa_results)
        df.to_csv(QA_OUTPUT, index=False)
        
        # Save fiducials separately
        fiducial_data = {filepath: fiducials}
        if os.path.exists(FIDUCIAL_OUTPUT):
            with open(FIDUCIAL_OUTPUT, 'r') as f:
                all_fiducials = json.load(f)
        else:
            all_fiducials = {}
        
        all_fiducials.update(fiducial_data)
        
        with open(FIDUCIAL_OUTPUT, 'w') as f:
            json.dump(all_fiducials, f, indent=2)
    
    def load_image(self, filepath):
        """Load and prepare image for display"""
        img = Image.open(filepath)
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Downsample for display (keep aspect ratio)
        max_dim = 1200
        if max(img.size) > max_dim:
            ratio = max_dim / max(img.size)
            new_size = tuple(int(dim * ratio) for dim in img.size)
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        return np.array(img)
    
    def rotate_image(self, img, angle):
        """Rotate image by angle (degrees)"""
        img_pil = Image.fromarray(img)
        rotated = img_pil.rotate(angle, expand=True, fillcolor=(255, 255, 255))
        return np.array(rotated)
    
    def display_image(self):
        """Display current image with controls"""
        if self.current_idx >= len(self.image_files):
            print("No more images!")
            return
        
        filepath = self.image_files[self.current_idx]
        year = Path(filepath).parent.parent.name
        dataset = Path(filepath).parent.name
        filename = Path(filepath).name
        
        # Load existing QA
        existing_qa = self.get_qa_for_image(filepath)
        if existing_qa:
            self.rotation = existing_qa['Rotation']
            status_text = f"[{existing_qa['Status']}]"
        else:
            self.rotation = 0
            status_text = "[NOT REVIEWED]"
        
        # Create UI
        clear_output(wait=True)
        
        # Info display
        info_html = f"""
        <div style='background: #f0f0f0; padding: 10px; margin-bottom: 10px;'>
        <b>Image {self.current_idx + 1} of {len(self.image_files)}</b> {status_text}<br>
        <b>Year:</b> {year} | <b>Dataset:</b> {dataset}<br>
        <b>File:</b> {filename}
        </div>
        """
        display(widgets.HTML(info_html))
        
        # Load and display image
        img = self.load_image(filepath)
        rotated_img = self.rotate_image(img, self.rotation)
        
        # Create matplotlib figure
        self.fig, self.ax = plt.subplots(figsize=(12, 10))
        self.img_display = self.ax.imshow(rotated_img)
        self.ax.set_title(f'{filename} (Rotation: {self.rotation}°)', fontsize=10)
        self.ax.axis('off')
        
        # Draw existing fiducials
        self.fiducial_circles = []
        for fid in self.fiducials:
            circle = Circle((fid['x'], fid['y']), 20, color='red', fill=False, linewidth=2)
            self.ax.add_patch(circle)
            self.fiducial_circles.append(circle)
        
        # Click handler for fiducial marking
        self.fig.canvas.mpl_connect('button_press_event', self.on_click)
        
        plt.tight_layout()
        plt.show()
        
        # Controls
        self.create_controls()
    
    def on_click(self, event):
        """Handle click to add fiducial mark"""
        if event.inaxes != self.ax:
            return
        
        if event.button == 1:  # Left click - add fiducial
            x, y = event.xdata, event.ydata
            self.fiducials.append({'x': x, 'y': y})
            
            # Draw circle
            circle = Circle((x, y), 20, color='red', fill=False, linewidth=2)
            self.ax.add_patch(circle)
            self.fiducial_circles.append(circle)
            self.fig.canvas.draw()
            
            print(f"✓ Fiducial added at ({x:.0f}, {y:.0f}) - Total: {len(self.fiducials)}")
        
        elif event.button == 3:  # Right click - remove last fiducial
            if self.fiducials:
                self.fiducials.pop()
                if self.fiducial_circles:
                    self.fiducial_circles[-1].remove()
                    self.fiducial_circles.pop()
                self.fig.canvas.draw()
                print(f"✗ Fiducial removed - Total: {len(self.fiducials)}")
    
    def create_controls(self):
        """Create control buttons"""
        
        # Rotation slider
        rotation_slider = widgets.IntSlider(
            value=self.rotation,
            min=0,
            max=360,
            step=1,
            description='Rotate:',
            continuous_update=False
        )
        
        def on_rotation_change(change):
            self.rotation = change['new']
            self.display_image()
        
        rotation_slider.observe(on_rotation_change, names='value')
        
        # Quick rotation buttons
        rotate_90_btn = widgets.Button(description='Rotate 90° CW')
        rotate_270_btn = widgets.Button(description='Rotate 90° CCW')
        rotate_180_btn = widgets.Button(description='Rotate 180°')
        
        def rotate_90(b):
            self.rotation = (self.rotation + 90) % 360
            rotation_slider.value = self.rotation
            self.display_image()
        
        def rotate_270(b):
            self.rotation = (self.rotation - 90) % 360
            rotation_slider.value = self.rotation
            self.display_image()
        
        def rotate_180(b):
            self.rotation = (self.rotation + 180) % 360
            rotation_slider.value = self.rotation
            self.display_image()
        
        rotate_90_btn.on_click(rotate_90)
        rotate_270_btn.on_click(rotate_270)
        rotate_180_btn.on_click(rotate_180)
        
        # Accept/Reject buttons
        accept_btn = widgets.Button(
            description='✓ Accept',
            button_style='success',
            layout=widgets.Layout(width='150px')
        )
        
        reject_btn = widgets.Button(
            description='✗ Reject',
            button_style='danger',
            layout=widgets.Layout(width='150px')
        )
        
        skip_btn = widgets.Button(
            description='Skip',
            button_style='warning',
            layout=widgets.Layout(width='150px')
        )
        
        def accept_image(b):
            filepath = self.image_files[self.current_idx]
            self.save_qa_result(filepath, 'ACCEPT', self.rotation, self.fiducials)
            print(f"✓ Image ACCEPTED with {len(self.fiducials)} fiducials")
            self.fiducials = []
            self.next_image()
        
        def reject_image(b):
            filepath = self.image_files[self.current_idx]
            self.save_qa_result(filepath, 'REJECT', self.rotation, [])
            print(f"✗ Image REJECTED")
            self.fiducials = []
            self.next_image()
        
        def skip_image(b):
            print("⊙ Image SKIPPED")
            self.fiducials = []
            self.next_image()
        
        accept_btn.on_click(accept_image)
        reject_btn.on_click(reject_image)
        skip_btn.on_click(skip_image)
        
        # Navigation buttons
        prev_btn = widgets.Button(description='◀ Previous')
        next_btn = widgets.Button(description='Next ▶')
        
        def prev_image(b):
            self.fiducials = []
            self.current_idx = max(0, self.current_idx - 1)
            self.display_image()
        
        def next_image_click(b):
            self.fiducials = []
            self.next_image()
        
        prev_btn.on_click(prev_image)
        next_btn.on_click(next_image_click)
        
        # Layout
        display(widgets.HTML("<b>Rotation Controls:</b>"))
        display(widgets.HBox([rotate_270_btn, rotate_90_btn, rotate_180_btn]))
        display(rotation_slider)
        
        display(widgets.HTML("<br><b>Fiducial Marking:</b> Left-click to add, Right-click to remove last"))
        
        display(widgets.HTML("<br><b>Quality Assessment:</b>"))
        display(widgets.HBox([accept_btn, reject_btn, skip_btn]))
        
        display(widgets.HTML("<br><b>Navigation:</b>"))
        display(widgets.HBox([prev_btn, next_btn]))
    
    def next_image(self):
        """Move to next image"""
        self.current_idx += 1
        if self.current_idx < len(self.image_files):
            self.display_image()
        else:
            print("\n" + "="*70)
            print("ALL IMAGES REVIEWED!")
            print("="*70)
            self.show_summary()
    
    def show_summary(self):
        """Show QA summary"""
        if not self.qa_results:
            print("\nNo images reviewed yet")
            return
        
        df = pd.DataFrame(self.qa_results)
        
        print(f"\nTotal reviewed: {len(df)}")
        print(f"Accepted: {len(df[df['Status'] == 'ACCEPT'])}")
        print(f"Rejected: {len(df[df['Status'] == 'REJECT'])}")
        
        print("\nBy year:")
        summary = df.groupby('Year')['Status'].value_counts().unstack(fill_value=0)
        print(summary)
        
        print(f"\nResults saved to: {QA_OUTPUT}")
        print(f"Fiducials saved to: {FIDUCIAL_OUTPUT}")

# ============================================================================
# Main
# ============================================================================

def start_viewer():
    """Start the image viewer"""
    viewer = ImageViewer(IMAGE_DIR)
    viewer.display_image()
    return viewer

# Run viewer
print("Starting Image Viewer...")
print("="*70)
print("CONTROLS:")
print("- Rotate: Use slider or quick rotation buttons")
print("- Fiducials: Left-click to add, Right-click to remove last")
print("- Accept: Keep image for processing")
print("- Reject: Exclude image from processing")
print("- Skip: Move to next without decision")
print("="*70)
print()

viewer = start_viewer()
