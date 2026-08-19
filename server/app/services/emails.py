"""邮件服务 —— 6 个 DTC 事务/营销模板内联渲染 + MVP 日志投递（接 Resend 时仅改 deliver 内部）"""

import logging

from jinja2 import Environment

log = logging.getLogger("glowmag.emails")

env = Environment(autoescape=True)

_FOOTER = (
    '<hr style="border:none;border-top:1px solid #eee;margin:24px 0">'
    '<p style="color:#999;font-size:12px;line-height:1.6">'
    "GLOWMAG &middot; Press-on nails, made to glow<br>"
    '<a href="https://glowmag.example/shop">Shop</a> &middot; '
    '<a href="https://glowmag.example/help">Help</a> &middot; '
    '<a href="https://glowmag.example/unsubscribe?email={{ email }}">Unsubscribe</a><br>'
    "&copy; GLOWMAG, 123 Glow Lane, Los Angeles, CA &middot; You receive this at {{ email }}"
    "</p>"
)

_BODIES = {
    "order_paid": """
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto">
      <h2 style="letter-spacing:3px;margin-bottom:4px">GLOWMAG</h2>
      <p>Hi {{ email }},</p>
      <p>Great news &mdash; your order <strong>{{ order_no }}</strong> is confirmed!
         Total: <strong>${{ '%.2f'|format(grand_total / 100) }}</strong>.</p>
      <p>We're hand-checking every set and will email you the moment your parcel ships.
         Typical delivery is 3&ndash;5 business days after dispatch.</p>
      <p style="margin:28px 0"><a href="https://glowmag.example/orders/{{ order_no }}"
         style="background:#000;color:#fff;padding:12px 28px;text-decoration:none">Track order</a></p>
      <p>Stay glowing,<br>The GLOWMAG Team</p>
    </div>
    """,
    "order_shipped": """
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto">
      <h2 style="letter-spacing:3px;margin-bottom:4px">GLOWMAG</h2>
      <p>Hi {{ email }},</p>
      <p>Your order <strong>{{ order_no }}</strong> is on its way via <strong>{{ carrier|upper }}</strong>!</p>
      <p>Tracking number: <strong>{{ tracking_no }}</strong> &mdash; allow up to 24h for the carrier
         to show movement.</p>
      <p style="margin:28px 0"><a href="https://glowmag.example/orders/{{ order_no }}"
         style="background:#000;color:#fff;padding:12px 28px;text-decoration:none">Track parcel</a></p>
      <p>Stay glowing,<br>The GLOWMAG Team</p>
    </div>
    """,
    "order_refunded": """
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto">
      <h2 style="letter-spacing:3px;margin-bottom:4px">GLOWMAG</h2>
      <p>Hi {{ email }},</p>
      <p>We've processed a refund of <strong>${{ '%.2f'|format(amount / 100) }}</strong>
         for order <strong>{{ order_no }}</strong>
         {% if reason %}(reason: {{ reason }}){% endif %}.</p>
      <p>Your bank typically posts it within 3&ndash;5 business days. Any points used on
         this order have been returned to your GLOWMAG account.</p>
      <p>We'd love to make it right next time &mdash; replies go straight to a human.</p>
      <p>Stay glowing,<br>The GLOWMAG Team</p>
    </div>
    """,
    "abandoned_cart": """
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto">
      <h2 style="letter-spacing:3px;margin-bottom:4px">GLOWMAG</h2>
      <p>Hi {{ email }},</p>
      {% if stage == 2 %}
      <p><strong>Still thinking? Here's more off.</strong> We've bumped your discount to
         <strong>15% off</strong> &mdash; because your favorites shouldn't wait any longer:</p>
      <ul>
        {% for item in items %}
        <li>{{ item.title }} &times; {{ item.qty }}</li>
        {% endfor %}
      </ul>
      <p>Use this code at checkout:</p>
      <p style="font-size:24px;letter-spacing:4px;font-weight:bold;background:#f7f7f7;
                padding:14px;text-align:center">{{ coupon_code }}</p>
      {% elif stage == 3 %}
      <p><strong>Last call &mdash; your cart items are almost gone.</strong> Here's what's still
         holding on for you:</p>
      <ul>
        {% for item in items %}
        <li>{{ item.title }} &times; {{ item.qty }} &mdash; only {{ item.stock }} left</li>
        {% endfor %}
      </ul>
      <p>These sets are selling fast and we can't hold your stock once it runs out.
         This is your final heads-up.</p>
      {% else %}
      <p><strong>Your cart misses you.</strong> Your picks are still waiting:</p>
      <ul>
        {% for item in items %}
        <li>{{ item.title }} &times; {{ item.qty }}</li>
        {% endfor %}
      </ul>
      {% if coupon_code %}
      <p>Here's <strong>10% off</strong> to sweeten the deal &mdash; code
         <strong>{{ coupon_code }}</strong>, valid for a short time:</p>
      {% endif %}
      {% endif %}
      <p style="margin:28px 0"><a href="{{ recovery_link }}"
         style="background:#000;color:#fff;padding:12px 28px;text-decoration:none">{% if stage == 3 %}Complete my order{% else %}Recover my cart{% endif %}</a></p>
      {% if stage != 3 %}<p>Stock moves fast on best-sellers, so don't wait too long.</p>{% endif %}
      <p>Stay glowing,<br>The GLOWMAG Team</p>
    </div>
    """,
    "welcome_coupon": """
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto">
      <h2 style="letter-spacing:3px;margin-bottom:4px">GLOWMAG</h2>
      <p>Hi {{ email }},</p>
      <p>Welcome to the GLOWMAG club &mdash; where salon-grade press-on nails meet your couch.</p>
      <p>Here's <strong>{{ discount }}% off</strong> your first set with code:</p>
      <p style="font-size:24px;letter-spacing:4px;font-weight:bold;background:#f7f7f7;
                padding:14px;text-align:center">{{ code }}</p>
      <p style="margin:28px 0"><a href="https://glowmag.example/shop"
         style="background:#000;color:#fff;padding:12px 28px;text-decoration:none">Shop new arrivals</a></p>
      <p>Earn 10 points for every $1 and unlock birthday gifts along the way.</p>
      <p>Stay glowing,<br>The GLOWMAG Team</p>
    </div>
    """,
    "restock_notify": """
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto">
      <h2 style="letter-spacing:3px;margin-bottom:4px">GLOWMAG</h2>
      <p>Hi {{ email }},</p>
      <p>Good news &mdash; <strong>{{ product_title }}</strong>{% if variant %} ({{ variant }}){% endif %}
         is back in stock!</p>
      <p>You asked, we restocked. Last time it sold out in days, so grab yours now:</p>
      <p style="margin:28px 0"><a href="https://glowmag.example/shop"
         style="background:#000;color:#fff;padding:12px 28px;text-decoration:none">Shop now</a></p>
      <p>Stay glowing,<br>The GLOWMAG Team</p>
    </div>
    """,
    "password_reset": """
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto">
      <h2 style="letter-spacing:3px;margin-bottom:4px">GLOWMAG</h2>
      <p>Hi {{ email }},</p>
      <p>We got a request to reset your GLOWMAG password. This link expires in
         <strong>15 minutes</strong>:</p>
      <p style="margin:28px 0"><a href="{{ reset_link }}"
         style="background:#000;color:#fff;padding:12px 28px;text-decoration:none">Reset my password</a></p>
      <p>Didn't ask for this? Just ignore this email &mdash; your password stays unchanged.</p>
      <p>Stay glowing,<br>The GLOWMAG Team</p>
    </div>
    """,
}

_BODIES["daily_digest"] = """
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto">
      <h2 style="letter-spacing:3px;margin-bottom:4px">GLOWMAG</h2>
      <h3 style="margin:16px 0 4px">Daily Digest &mdash; {{ date }} (UTC)</h3>
      <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:12px">
        <tr style="background:#f7f7f7">
          <th style="text-align:left;padding:6px 8px;border:1px solid #eee">Sales</th>
          <th style="text-align:right;padding:6px 8px;border:1px solid #eee">Value</th>
        </tr>
        <tr><td style="padding:6px 8px;border:1px solid #eee">GMV</td>
            <td style="text-align:right;padding:6px 8px;border:1px solid #eee">${{ '%.2f'|format(gmv / 100) }}</td></tr>
        <tr><td style="padding:6px 8px;border:1px solid #eee">Orders placed</td>
            <td style="text-align:right;padding:6px 8px;border:1px solid #eee">{{ orders }}</td></tr>
        <tr><td style="padding:6px 8px;border:1px solid #eee">Paid orders</td>
            <td style="text-align:right;padding:6px 8px;border:1px solid #eee">{{ paid_count }}</td></tr>
        <tr><td style="padding:6px 8px;border:1px solid #eee">Refunds</td>
            <td style="text-align:right;padding:6px 8px;border:1px solid #eee">{{ refund_count }} (${{ '%.2f'|format(refund_amount / 100) }})</td></tr>
        <tr><td style="padding:6px 8px;border:1px solid #eee">New users</td>
            <td style="text-align:right;padding:6px 8px;border:1px solid #eee">{{ new_users }}</td></tr>
        <tr><td style="padding:6px 8px;border:1px solid #eee">New abandoned carts</td>
            <td style="text-align:right;padding:6px 8px;border:1px solid #eee">{{ abandoned_new }}</td></tr>
      </table>
      <h3 style="margin:16px 0 4px">Pending queue</h3>
      <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:12px">
        {% for row in todos %}
        <tr><td style="padding:6px 8px;border:1px solid #eee">{{ row.name }}</td>
            <td style="text-align:right;padding:6px 8px;border:1px solid #eee">{{ row.count }}</td></tr>
        {% endfor %}
      </table>
      <h3 style="margin:16px 0 4px">Top products</h3>
      <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:12px">
        {% for p in top_products %}
        <tr><td style="padding:6px 8px;border:1px solid #eee">#{{ loop.index }} {{ p.title }}</td>
            <td style="text-align:right;padding:6px 8px;border:1px solid #eee">{{ p.qty }} sold</td></tr>
        {% else %}
        <tr><td style="padding:6px 8px;border:1px solid #eee">No paid orders yesterday</td>
            <td style="text-align:right;padding:6px 8px;border:1px solid #eee">0</td></tr>
        {% endfor %}
      </table>
      <h3 style="margin:16px 0 4px">Inventory</h3>
      <p style="font-size:14px">Low stock alerts (stock &le; 8): <strong>{{ low_stock_count }}</strong></p>
      <p style="font-size:12px;color:#999">Auto-generated by the GLOWMAG worker &middot; window {{ date }} 00:00&ndash;24:00 UTC</p>
      <p>Stay glowing,<br>The GLOWMAG Team</p>
    </div>
    """

TEMPLATES = {name: body + _FOOTER for name, body in _BODIES.items()}


def render(name: str, **ctx) -> str:
    return env.from_string(TEMPLATES[name]).render(**ctx)


def deliver(to: str, subject: str, html: str) -> None:
    log.info("[EMAIL] to=%s subject=%s\n%s", to, subject, html)
