"""Simple test script for hand-drawn annotations (no OCR dependency)"""
from pathlib import Path
from PIL import Image, ImageDraw
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from grading.annotator import (
    draw_handdrawn_checkmark, 
    draw_handdrawn_x, 
    draw_handdrawn_partial,
    _draw_score_circles,
    HANDDRAWN_COLOR
)

# Create a test image (simulating a student answer sheet)
width, height = 800, 1000
img = Image.new('RGB', (width, height), color='white')
draw = ImageDraw.Draw(img)

# Draw some horizontal lines like lined paper
for y in range(50, height, 40):
    draw.line([(50, y), (width - 50, y)], fill=(200, 200, 200), width=1)

# Define test answer regions (bounding boxes)
answer_regions = [
    [100, 100, 600, 180],   # Answer 1 - will get checkmark
    [100, 220, 600, 300],   # Answer 2 - will get X
    [100, 340, 600, 420],   # Answer 3 - will get partial
    [100, 460, 700, 560],   # Answer 4 - larger region, checkmark
    [100, 600, 500, 680],   # Answer 5 - smaller region, checkmark
]

# Draw the hand-drawn annotations
print("Drawing hand-drawn annotations...")

# Checkmark on answer 1
draw_handdrawn_checkmark(draw, answer_regions[0])
print("  [OK] Drew checkmark on region 1")

# X on answer 2
draw_handdrawn_x(draw, answer_regions[1])
print("  [X] Drew X on region 2")

# Partial on answer 3
draw_handdrawn_partial(draw, answer_regions[2])
print("  [~] Drew partial on region 3")

# More checkmarks
draw_handdrawn_checkmark(draw, answer_regions[3])
print("  [OK] Drew checkmark on region 4")

draw_handdrawn_checkmark(draw, answer_regions[4])
print("  [OK] Drew checkmark on region 5")

# Draw score circles (simulating midterm mode)
_draw_score_circles(draw, score=8, max_score=10, running_total=(45, 100))
print("  [SCORE] Drew score circles (8/10 and 45/100)")

# Save the test image
output_path = Path(__file__).parent / "test_output_handdrawn.png"
img.save(output_path)
print(f"\n✅ Test image saved to: {output_path}")
print(f"   Open this file to see the hand-drawn annotations!")
