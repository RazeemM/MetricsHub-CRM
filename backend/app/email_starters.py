"""Starter designs for new email templates. Table-based, inline styles, 600 px wide: renders in Outlook and Gmail."""

_SHELL = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{title}}</title></head>
<body style="margin:0;padding:0;background:#f2f4f7">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f2f4f7">
<tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:8px;overflow:hidden;font-family:Segoe UI,Arial,sans-serif;color:#1f2933">
<tr><td style="background:{{color}};padding:20px 28px;color:#ffffff;font-size:20px;font-weight:bold">{{brand}}</td></tr>
{{content}}
</table>
<p style="font-family:Arial,sans-serif;font-size:12px;color:#888;margin:16px 0 0">
{{brand}} &middot; {postal_address} &middot; <a href="{unsubscribe_url}" style="color:#888">Unsubscribe</a></p>
</td></tr></table>
</body></html>"""

_NEWSLETTER = """<tr><td style="padding:28px 28px 8px;font-size:15px;line-height:1.6">
<p style="margin:0 0 16px">Hi {first_name|there},</p>
<p style="margin:0 0 16px">Here is what is new this month.</p>
</td></tr>
<tr><td style="padding:8px 28px">
<h2 style="font-size:18px;margin:0 0 8px">Headline of the first story</h2>
<p style="font-size:15px;line-height:1.6;margin:0 0 12px">Two or three sentences about it.</p>
<a href="https://example.com/first-story" style="display:inline-block;background:{{color}};color:#ffffff;text-decoration:none;padding:10px 18px;border-radius:6px;font-size:14px">Read more</a>
</td></tr>
<tr><td style="padding:24px 28px 8px">
<h2 style="font-size:18px;margin:0 0 8px">Second story</h2>
<p style="font-size:15px;line-height:1.6;margin:0 0 12px">Short summary and a <a href="https://example.com/second" style="color:{{color}}">link</a>.</p>
</td></tr>
<tr><td style="padding:16px 28px 28px;font-size:15px;line-height:1.6">
<p style="margin:0">Best regards,<br>The {{brand}} team</p>
</td></tr>"""

_ANNOUNCEMENT = """<tr><td style="padding:28px;font-size:15px;line-height:1.6">
<p style="margin:0 0 16px">Dear {first_name|customer},</p>
<p style="margin:0 0 16px">Write your message here. Keep it short: one idea, one call to action.</p>
<p style="margin:0 0 24px"><a href="https://example.com" style="display:inline-block;background:{{color}};color:#ffffff;text-decoration:none;padding:12px 22px;border-radius:6px">Call to action</a></p>
<p style="margin:0">Kind regards,<br>{owner|The team}</p>
</td></tr>"""


def starters(brand: str = "MetricsHub", color: str = "#7C5CFF") -> list[dict]:
    def build(title, content):
        return (_SHELL.replace("{{content}}", content).replace("{{title}}", title)
                .replace("{{brand}}", brand).replace("{{color}}", color))
    return [
        {"key": "newsletter", "name": "Newsletter", "subject": f"{brand} news: [month]",
         "preheader": "What is new this month", "body_html": build("Newsletter", _NEWSLETTER)},
        {"key": "announcement", "name": "Announcement", "subject": "[Subject]",
         "preheader": "", "body_html": build("Announcement", _ANNOUNCEMENT)},
        {"key": "blank", "name": "Blank", "subject": "", "preheader": "", "body_html": build("Email", "")},
    ]
