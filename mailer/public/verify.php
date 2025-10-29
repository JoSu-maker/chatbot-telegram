<?php
// Token validator & redirector for QR links
// Usage: /verify.php?t=<sig>.<payload_b64>.<nonce>
// Env:
// - QR_SECRET: HMAC secret (must match bot)
// - QR_TTL_SECONDS: token validity in seconds (default 604800 = 7 days)
// - QR_REDIRECT_BASE: where to redirect after validation (default https://app.authenology.com.ve)

header('Cache-Control: no-store');

$secret = getenv('QR_SECRET') ?: '';
$ttl = intval(getenv('QR_TTL_SECONDS') ?: '604800');
$redirectBase = getenv('QR_REDIRECT_BASE') ?: 'https://app.authenology.com.ve';

function b64url_decode_str(string $s): string {
    $pad = strlen($s) % 4;
    if ($pad) $s .= str_repeat('=', 4 - $pad);
    return base64_decode(strtr($s, '-_', '+/')) ?: '';
}

function timing_safe_equals(string $a, string $b): bool {
    if (function_exists('hash_equals')) return hash_equals($a, $b);
    if (strlen($a) !== strlen($b)) return false;
    $res = 0;
    for ($i = 0; $i < strlen($a); $i++) { $res |= ord($a[$i]) ^ ord($b[$i]); }
    return $res === 0;
}

$t = $_GET['t'] ?? '';
if (!is_string($t) || $t === '') {
    http_response_code(400);
    echo 'Missing token';
    exit;
}

$parts = explode('.', $t);
if (count($parts) !== 3) {
    http_response_code(400);
    echo 'Invalid token format';
    exit;
}
[$sig_b64, $payload_b64, $nonce] = $parts;
$payload_json = b64url_decode_str($payload_b64);
if ($payload_json === '') {
    http_response_code(400);
    echo 'Invalid payload';
    exit;
}

$data = json_decode($payload_json, true);
if (!is_array($data)) {
    http_response_code(400);
    echo 'Malformed payload';
    exit;
}

$ts = isset($data['ts']) ? intval($data['ts']) : 0;
if ($ts <= 0) {
    http_response_code(400);
    echo 'Missing timestamp';
    exit;
}

// TTL check
if ($ttl > 0 && (time() - $ts) > $ttl) {
    http_response_code(410); // Gone
    echo 'Token expired';
    exit;
}

if ($secret) {
    $calc_sig = base64_encode(hash_hmac('sha256', json_encode($data, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION | JSON_UNESCAPED_UNICODE), $secret, true));
    $calc_sig = rtrim(strtr($calc_sig, '+/', '-_'), '=');
    if (!timing_safe_equals($calc_sig, $sig_b64)) {
        http_response_code(401);
        echo 'Invalid signature';
        exit;
    }
}

// Build redirect URL with minimal context
$q = http_build_query([
    'e' => $data['e'] ?? '',
    'ts' => $ts,
]);
$location = rtrim($redirectBase, '/') . '/?' . $q;
header('Location: ' . $location, true, 302);
exit;
