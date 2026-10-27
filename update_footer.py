import re

# Process o-nas.html
with open('templates/o-nas.html', 'r', encoding='utf-8') as f:
    content = f.read()

old_footer = '''<footer class="fixed-bottom" style="background-color: black; padding: 15px; padding-bottom: 2px;">
        <div style="text-align: center; color: white; display: flex; justify-content: center; flex-wrap: wrap; gap: 12px;">
            <p style="margin: 0 8px 0 0;"><a href="/o-nas" style="color: white; text-decoration: underline;">O nas</a></p>
            <p style="margin: 0 8px 0 0;"><a href="/faq" style="color: white; text-decoration: underline;">FAQ</a></p>
        </div>
        <p style="text-align: center; color: white; margin-top: 5px;">Beležka - Kajba</p>
    </footer>'''

new_footer = '''<footer class="fixed-bottom" style="background-color: black; padding: 15px; padding-bottom: 2px;">
        <div style="display: flex; justify-content: center; align-items: center; gap: 12px;">
            <p style="margin: 0;"><a href="/o-nas" style="color: white; text-decoration: underline; margin-right: 20px;">O nas</a></p>
            <span style="color: white; margin: 0 10px;">Beležka - Kajba</span>
            <p style="margin: 0;"><a href="/faq" style="color: white; text-decoration: underline; margin-left: 20px;">FAQ</a></p>
        </div>
    </footer>'''

content = content.replace(old_footer, new_footer)

with open('templates/o-nas.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('o-nas.html updated')

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