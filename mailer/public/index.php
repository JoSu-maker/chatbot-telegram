<?php
require __DIR__ . '/../vendor/autoload.php';

use PHPMailer\PHPMailer\PHPMailer;
use PHPMailer\PHPMailer\Exception;

// QR Code dependencies
use Endroid\QrCode\QrCode;
use Endroid\QrCode\Encoding\Encoding;
use Endroid\QrCode\ErrorCorrectionLevel\ErrorCorrectionLevelHigh;
use Endroid\QrCode\Color\Color;
use Endroid\QrCode\Writer\PngWriter;
use Endroid\QrCode\RoundBlockSizeMode\RoundBlockSizeModeMargin;
use Endroid\QrCode\Logo\Logo;

header('Content-Type: application/json');

// simple debug logger
$MAILER_DEBUG = strtolower(getenv('MAILER_DEBUG') ?: 'false') === 'true';
$LOG_FILE = '/tmp/mailer.log';
$logf = function(string $msg) use ($MAILER_DEBUG, $LOG_FILE) {
    if ($MAILER_DEBUG) {
        @file_put_contents($LOG_FILE, '[' . date('c') . "] " . $msg . "\n", FILE_APPEND);
    }
};

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
if ($method !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method Not Allowed']);
    exit;
}

$raw = file_get_contents('php://input');
$data = json_decode($raw, true);
if (!is_array($data)) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Invalid JSON']);
    exit;
}
$logf('Incoming payload keys: ' . implode(',', array_keys($data)));

$to = $data['to_email'] ?? '';
$subject = $data['subject'] ?? '';
$message = $data['message'] ?? '';
$fromEmail = $data['from_email'] ?? getenv('SMTP_FROM') ?: '';
$fromName = $data['from_name'] ?? getenv('SMTP_FROM_NAME') ?: 'Authenology Bot';
$replyTo = $data['reply_to'] ?? '';

// Optional QR parameters
$qrUrl = $data['qr_url'] ?? '';
$qrSeed = $data['qr_seed'] ?? ($data['user_id'] ?? $to);
$qrSize = intval($data['qr_size'] ?? 260);
// Optional logo URL (default to provided company logo)
$logoUrl = $data['logo_url'] ?? 'https://app.authenology.com.ve/imagenes/logo01.png';
if ($qrSize < 100) { $qrSize = 100; }
if ($qrSize > 600) { $qrSize = 600; }
// Provide a sensible default URL so QR is always present unless explicitly disabled
if (!is_string($qrUrl) || $qrUrl === '') {
    $qrUrl = 'https://app.authenology.com.ve';
}

if (!$to || !$subject || !$message || !$fromEmail) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Missing fields: to_email, subject, message, from_email']);
    exit;
}

$smtpHost = getenv('SMTP_HOST') ?: '';
$smtpPort = intval(getenv('SMTP_PORT') ?: '587');
$smtpUser = getenv('SMTP_USER') ?: '';
$smtpPass = getenv('SMTP_PASS') ?: '';
$smtpSecure = getenv('SMTP_SECURE') ?: 'tls'; // tls|ssl|empty
$smtpAuthDisabled = strtolower(getenv('SMTP_AUTH') ?: 'true') === 'false'; // set SMTP_AUTH=false para deshabilitar auth

// Opciones para certificados autofirmados (se puede activar depende del uso)
$allowSelfSigned = strtolower(getenv('SMTP_ALLOW_SELF_SIGNED') ?: 'false') === 'true';
$verifyPeer = strtolower(getenv('SMTP_VERIFY_PEER') ?: 'true') === 'true';
$verifyPeerName = strtolower(getenv('SMTP_VERIFY_PEER_NAME') ?: 'true') === 'true';

if (!$smtpHost) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'SMTP not configured']);
    exit;
}

$mail = new PHPMailer(true);
try {
    // Server settings
    $mail->isSMTP();
    // Idioma y codificación para acentos correctos
    $mail->CharSet = 'UTF-8';
    $mail->Encoding = 'base64';
    // $mail->setLanguage('es'); // opcional
    $mail->Host = $smtpHost;
    $mail->Port = $smtpPort;
    if (!$smtpAuthDisabled && $smtpUser !== '' && $smtpPass !== '') {
        $mail->SMTPAuth = true;
        $mail->Username = $smtpUser;
        $mail->Password = $smtpPass;
    } else {
        $mail->SMTPAuth = false;
    }
    if ($smtpSecure === 'tls' || $smtpSecure === 'ssl') {
        $mail->SMTPSecure = $smtpSecure;
    }
    if ($allowSelfSigned || !$verifyPeer || !$verifyPeerName) {
        $mail->SMTPOptions = [
            'ssl' => [
                'verify_peer' => $verifyPeer,
                'verify_peer_name' => $verifyPeerName,
                'allow_self_signed' => $allowSelfSigned,
            ],
        ];
    }

    // Sender/Recipients
    $mail->setFrom($fromEmail, $fromName);
    $mail->addAddress($to);
    if ($replyTo) {
        $mail->addReplyTo($replyTo);
    }

    // Prepare optional QR embedding
    $qrCid = null;
    $qrHtmlBlock = '';
    if (is_string($qrUrl) && $qrUrl !== '') {
        // Deterministic color from seed (simple hash -> RGB)
        $seed = (string)$qrSeed;
        $hash = sha1($seed ?: $to);
        $r = hexdec(substr($hash, 0, 2));
        $g = hexdec(substr($hash, 2, 2));
        $b = hexdec(substr($hash, 4, 2));
        // Keep colors not too light
        $r = max(30, $r); $g = max(30, $g); $b = max(30, $b);

        $qr = QrCode::create($qrUrl)
            ->setEncoding(new Encoding('UTF-8'))
            ->setErrorCorrectionLevel(new ErrorCorrectionLevelHigh())
            ->setSize($qrSize)
            ->setMargin(10)
            ->setRoundBlockSizeMode(new RoundBlockSizeModeMargin())
            ->setForegroundColor(new Color($r, $g, $b))
            ->setBackgroundColor(new Color(255, 255, 255));

        $writer = new PngWriter();

        // Try to download and apply logo at center
        $logo = null;
        if (is_string($logoUrl) && $logoUrl !== '') {
            try {
                $imgData = @file_get_contents($logoUrl);
                if ($imgData !== false && strlen($imgData) > 0) {
                    $tmpPath = tempnam(sys_get_temp_dir(), 'qrlogo_');
                    // best effort write
                    if (@file_put_contents($tmpPath, $imgData) !== false) {
                        $targetWidth = max(40, (int)round($qrSize * 0.25));
                        $logo = Logo::create($tmpPath)
                            ->setResizeToWidth($targetWidth)
                            ->setPunchoutBackground(true);
                        $logf('Logo applied width=' . $targetWidth);
                    }
                }
            } catch (\Throwable $e) {
                // ignore logo errors
                $logo = null;
                $logf('Logo error: ' . $e->getMessage());
            }
        }

        $result = $writer->write($qr, $logo, null);
        $qrBinary = $result->getString();

        $qrCid = 'qr_' . bin2hex(random_bytes(6)) . '@authenology';
        $mail->addStringEmbeddedImage($qrBinary, $qrCid, 'qr.png', 'base64', 'image/png');
        $qrHtmlBlock = '<div style="margin-top:16px;text-align:center">'
            . '<p style="font-family:Arial,Helvetica,sans-serif;color:#333">Escanea el QR para continuar:</p>'
            . '<img src="cid:' . htmlspecialchars($qrCid, ENT_QUOTES, 'UTF-8') . '" alt="QR" width="' . intval($qrSize) . '" height="' . intval($qrSize) . '" style="display:inline-block;max-width:100%;height:auto;border-radius:12px" />'
            . '<p style="font-family:Arial,Helvetica,sans-serif;color:#666;font-size:12px">O abre: '
            . htmlspecialchars($qrUrl, ENT_QUOTES, 'UTF-8') . '</p>'
            . '</div>';
    }

    // Content
    $mail->Subject = $subject;
    if (isset($data['html']) && is_string($data['html']) && $data['html'] !== '') {
        $mail->isHTML(true);
        $bodyHtml = $data['html'];
        if ($qrHtmlBlock !== '') {
            // If template provides a placeholder for QR, replace it; else append at the end
            if (strpos($bodyHtml, '{{QR_BLOCK}}') !== false) {
                $bodyHtml = str_replace('{{QR_BLOCK}}', $qrHtmlBlock, $bodyHtml);
            } elseif (strpos($bodyHtml, '<!--QR_BLOCK-->') !== false) {
                $bodyHtml = str_replace('<!--QR_BLOCK-->', $qrHtmlBlock, $bodyHtml);
            } else {
                $bodyHtml .= '\n<hr />\n' . $qrHtmlBlock;
            }
        }
        $mail->Body = $bodyHtml;
        $mail->AltBody = $message ?: strip_tags($bodyHtml);
    } else {
        // Build using centralized template
        $mail->isHTML(true);
        $safeText = nl2br(htmlspecialchars($message, ENT_QUOTES, 'UTF-8'));
        $ctaUrl = is_string($qrUrl) && $qrUrl !== '' ? $qrUrl : '';
        $tplPath = __DIR__ . '/templates/base_email.php';
        $template = @file_get_contents($tplPath);
        if ($template === false) {
            $logf('Template not found at ' . $tplPath . ', using simple fallback.');
            $bodyHtml = '<div style="font-family:Arial,Helvetica,sans-serif">' . $safeText . '</div>' . ($qrHtmlBlock ?: '');
            $mail->Body = $bodyHtml;
            $mail->AltBody = $message . ($ctaUrl ? "\n\n" . 'Visita: ' . $ctaUrl : '');
        } else {
            $repl = [
                '{{SUBJECT}}' => htmlspecialchars($subject, ENT_QUOTES, 'UTF-8'),
                '{{LOGO_URL}}' => htmlspecialchars($logoUrl, ENT_QUOTES, 'UTF-8'),
                '{{CONTENT_HTML}}' => $safeText,
                '{{CTA_URL}}' => htmlspecialchars($ctaUrl, ENT_QUOTES, 'UTF-8'),
                '{{QR_BLOCK}}' => $qrHtmlBlock ?: '',
                '{{YEAR}}' => (string)date('Y'),
            ];
            $bodyHtml = strtr($template, $repl);
            $mail->Body = $bodyHtml;
            $mail->AltBody = $message . ($ctaUrl ? "\n\n" . 'Visita: ' . $ctaUrl : '');
        }
    }

    $mail->send();
    echo json_encode(['ok' => true]);
    $logf('Mail sent to ' . $to . ' subject=' . $subject);
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Mailer Error: ' . $mail->ErrorInfo]);
    $logf('Mailer exception: ' . $mail->ErrorInfo);
}
