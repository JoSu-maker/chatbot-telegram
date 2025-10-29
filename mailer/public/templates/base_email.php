<?php
// Base email template with placeholders:
// {{SUBJECT}}, {{LOGO_URL}}, {{CONTENT_HTML}}, {{CTA_URL}}, {{QR_BLOCK}}, {{YEAR}}
?>
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{SUBJECT}}</title>
</head>
<body style="margin:0;padding:0;background:#f5f7fb">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#f5f7fb">
    <tr><td align="center" style="padding:24px">
      <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:560px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 6px 24px rgba(0,0,0,0.08)">
        <tr>
          <td style="background:#0f172a;padding:20px;text-align:center">
            <img src="{{LOGO_URL}}" alt="Authenology" style="height:40px;max-width:100%" />
          </td>
        </tr>
        <tr>
          <td style="padding:24px 24px 8px 24px;font-family:Arial,Helvetica,sans-serif;color:#111827;font-size:15px;line-height:1.6">
            {{CONTENT_HTML}}
          </td>
        </tr>
        <tr>
          <td style="padding:0 24px 8px 24px;text-align:center">
            <?php if (!empty($ctaUrl)): ?>
              <a href="<?= htmlspecialchars($ctaUrl, ENT_QUOTES, 'UTF-8'); ?>" style="display:inline-block;padding:12px 20px;background:#0f172a;color:#fff;text-decoration:none;border-radius:8px">Abrir en Authenology</a>
            <?php endif; ?>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 24px 24px 24px">
            {{QR_BLOCK}}
          </td>
        </tr>
        <tr>
          <td style="background:#f3f4f6;padding:16px 24px;text-align:center;color:#6b7280;font-family:Arial,Helvetica,sans-serif;font-size:12px">
            © {{YEAR}} Authenology. Todos los derechos reservados.
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
  <div style="display:none;color:transparent;opacity:0;visibility:hidden;height:0;width:0">{{CTA_URL}}</div>
</body>
</html>
