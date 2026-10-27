#!/usr/bin/env python3
import os

# Process o-nas.html - replace footer links div
filepath = 'templates/o-nas.html'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Simple replacement - just change the div structure
old_div = '<div style="text-align: center; color: white; display: flex; justify-content: center; flex-wrap: wrap; gap: 12px;">\n            <p style="margin: 0 8px 0 0;"><a href="/o-nas" style="color: white; text-decoration: underline;">O nas</a></p>\n            <p style="margin: 0 8px 0 0;"><a href="/faq" style="color: white; text-decoration: underline;">FAQ</a></p>\n        </div>\n        <p style="text-align: center; color: white; margin-top: 5px;">Beležka - Kajba</p>'

new_div = '<div style="display: flex; justify-content: center; align-items: center; gap: 12px;">\n            <p style="margin: 0;"><a href="/o-nas" style="color: white; text-decoration: underline; margin-right: 20px;">O nas</a></p>\n            <span style="color: white; margin: 0 10px;">Beležka - Kajba</span>\n            <p style="margin: 0;"><a href="/faq" style="color: white; text-decoration: underline; margin-left: 20px;">FAQ</a></p>\n        </div>'

if old_div in content:
    content = content.replace(old_div, new_div)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print('o-nas.html updated successfully')
else:
    print('old_div not found, trying alternative...')
    # Try without the trailing newline
    old_div2 = '<div style="text-align: center; color: white; display: flex; justify-content: center; flex-wrap: wrap; gap: 12px;">\n            <p style="margin: 0 8px 0 0;"><a href="/o-nas" style="color: white; text-decoration: underline;">O nas</a></p>\n            <p style="margin: 0 8px 0 0;"><a href="/faq" style="color: white; text-decoration: underline;">FAQ</a></p>\n        </div>'
    if old_div2 in content:
        # Just replace the inner part
        content = content.replace(old_div2, '<div style="display: flex; justify-content: center; align-items: center; gap: 12px;">\n            <p style="margin: 0;"><a href="/o-nas" style="color: white; text-decoration: underline; margin-right: 20px;">O nas</a></p>\n            <span style="color: white; margin: 0 10px;">Beležka - Kajba</span>\n            <p style="margin: 0;"><a href="/faq" style="color: white; text-decoration: underline; margin-left: 20px;">FAQ</a></p>\n        </div>')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print('o-nas.html updated with alternative pattern')
    else:
        print('Could not find pattern in o-nas.html')

# Process faq.html
with open('templates/faq.html', 'r', encoding='utf-8') as f:
    content = f.read()

old_footer_faq = '''<footer class="fixed-bottom" style="background-color: black; padding: 15px; padding-bottom: 2px;">
        <div style="text-align: center; color: white; display: flex; justify-content: center; flex-wrap: wrap; gap: 12px;">
            <p style="margin: 0 8px 0 0;"><a href="/o-nas" style="color: white; text-decoration: underline;">O nas</a></p>
            <p style="margin: 0 8px 0 0;"><a href="/faq" style="color: white; text-decoration: underline;">FAQ</a></p>
        </div>
        <p style="text-align: center; color: white; margin-top: 5px;">Beležka - Kajba</p>
    </footer>'''

new_footer_faq = '''<footer class="fixed-bottom" style="background-color: black; padding: 15px; padding-bottom: 2px;">
        <div style="display: flex; justify-content: center; align-items: center; gap: 12px;">
            <p style="margin: 0;"><a href="/o-nas" style="color: white; text-decoration: underline; margin-right: 20px;">O nas</a></p>
            <span style="color: white; margin: 0 10px;">Beležka - Kajba</span>
            <p style="margin: 0;"><a href="/faq" style="color: white; text-decoration: underline; margin-left: 20px;">FAQ</a></p>
        </div>
    </footer>'''

content = content.replace(old_footer_faq, new_footer_faq)

with open('templates/faq.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('faq.html updated')