#!/usr/bin/env python3
"""Replace fetch_detail_page method in vandenbrug_scraper.py"""

# Read the original file
with open('/home/kltalsma/nl-car-tracker/scrapers/vandenbrug_scraper.py', 'r') as f:
    lines = f.readlines()

# Read the new method
with open('/home/kltalsma/nl-car-tracker/tmp/improved_fetch_detail_page.py', 'r') as f:
    new_method = f.read()

# Find the method boundaries
start_line = None
end_line = None

for i, line in enumerate(lines):
    if 'def fetch_detail_page(self, url: str) -> Dict:' in line:
        start_line = i
    elif start_line is not None and line.strip().startswith('def ') and i > start_line:
        end_line = i
        break

if start_line is None:
    print("ERROR: Could not find fetch_detail_page method")
    exit(1)

if end_line is None:
    print("ERROR: Could not find end of method")
    exit(1)

print(f"Found method at lines {start_line+1} to {end_line}")

# Replace the method
new_lines = lines[:start_line] + [new_method + '\n'] + lines[end_line:]

# Write the new file
with open('/home/kltalsma/nl-car-tracker/scrapers/vandenbrug_scraper.py', 'w') as f:
    f.writelines(new_lines)

print("Method replaced successfully!")
print(f"Old method: {end_line - start_line} lines")
print(f"New method: {len(new_method.splitlines())} lines")
