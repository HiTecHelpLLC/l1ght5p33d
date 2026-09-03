<?php
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 L1ght5p33d contributors
declare(strict_types=1);

require_once __DIR__ . '/../api/workflows/_catalog.php';

if (!function_exists('sodium_crypto_sign_keypair')) {
    throw new RuntimeException('Tests require PHP sodium; production fails closed without it.');
}

$checks = 0;
function registry_expect(bool $condition, string $message): void
{
    global $checks;
    $checks++;
    if (!$condition) throw new RuntimeException($message);
}

// Ephemeral synthetic signing material never leaves this test process.
$pair = sodium_crypto_sign_keypair();
$public = sodium_crypto_sign_publickey($pair);
$secret = sodium_crypto_sign_secretkey($pair);
$now = time();
$artifact = '{"schema_version":"l1ght5p33d/v1"}';
$sha = hash('sha256', $artifact);
$entry = [
    'id' => 'synthetic-poster', 'version' => '0.1.0-preview.1', 'title' => 'Synthetic poster',
    'description' => 'Harmless test metadata', 'application' => 'browser',
    'workflow_schema' => 'l1ght5p33d/v1', 'runtime_version' => '1.34.0', 'license' => 'MIT',
    'cid' => thebest_workflow_catalog_cid($sha), 'sha256' => $sha, 'size_bytes' => strlen($artifact),
    'compatibility' => (object) ['os' => 'Windows 11'],
    'verification' => ['level' => 'fixture', 'description' => 'Synthetic fixture only'],
];
$catalog = [
    'schema_version' => 'l1ght5p33d-catalog/v1', 'revision' => 1,
    'generated_at' => gmdate('Y-m-d\TH:i:s\Z', $now - 10),
    'expires_at' => gmdate('Y-m-d\TH:i:s\Z', $now + 3600),
    'workflows' => [$entry],
];
$sign = static function (array $value) use ($secret): string {
    $payload = json_encode($value, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES);
    return json_encode([
        'payload_b64' => base64_encode($payload),
        'signature_b64' => base64_encode(sodium_crypto_sign_detached($payload, $secret)),
    ], JSON_THROW_ON_ERROR | JSON_PRETTY_PRINT) . "\n";
};
$temporary = tempnam(sys_get_temp_dir(), 'workflow-registry-');
if ($temporary === false) throw new RuntimeException('Cannot create synthetic catalog');
$settings = [
    'THEBEST_WORKFLOW_REGISTRY_ENABLED' => '1',
    'THEBEST_WORKFLOW_CATALOG' => $temporary,
    'THEBEST_WORKFLOW_REGISTRY_PUBLIC_KEY' => bin2hex($public),
];
$root = dirname(__DIR__);
$request = static fn(string $method, array $config = []): array => thebest_workflow_registry_response($method, array_replace($settings, $config), $root, $now);
$reject = static function (array $value, string $message) use ($sign, $temporary, $request): void {
    file_put_contents($temporary, $sign($value));
    $response = $request('GET');
    registry_expect($response['status'] === 503 && $response['body'] === '{"error":"registry_unavailable"}', $message);
};
try {
    $raw = $sign($catalog);
    file_put_contents($temporary, $raw);
    $get = $request('GET');
    registry_expect($get['status'] === 200 && $get['body'] === $raw, 'GET must preserve the exact signed bytes');
    registry_expect($get['headers']['Content-Length'] === (string) strlen($raw), 'GET length must match signed bytes');
    $head = $request('HEAD');
    registry_expect($head['status'] === 200 && $head['body'] === '' && $head['headers']['Content-Length'] === (string) strlen($raw), 'HEAD must preserve GET headers without a body');
    registry_expect($request('POST')['status'] === 405, 'Enabled endpoint must reject mutation methods');
    registry_expect($request('OPTIONS')['status'] === 405, 'OPTIONS must not widen the route');
    registry_expect($request('GET', ['THEBEST_WORKFLOW_REGISTRY_ENABLED' => ''])['status'] === 404, 'Missing flag must disable discovery');
    registry_expect($request('POST', ['THEBEST_WORKFLOW_REGISTRY_ENABLED' => 'false'])['status'] === 404, 'Disabled endpoint must stay hidden for every method');
    registry_expect($request('GET', ['THEBEST_WORKFLOW_REGISTRY_PUBLIC_KEY' => str_repeat('0', 64)])['status'] === 503, 'Wrong public key must fail');
    registry_expect($request('GET', ['THEBEST_WORKFLOW_REGISTRY_PUBLIC_KEY' => ''])['status'] === 503, 'Missing public key must fail');
    registry_expect($request('GET', ['THEBEST_WORKFLOW_CATALOG' => $root . '/README.md'])['status'] === 503, 'Files under the web root must never be served');
    registry_expect($request('GET', ['THEBEST_WORKFLOW_CATALOG' => 'https://invalid.example/catalog.json'])['status'] === 503, 'Catalog paths cannot trigger a network fetch');
    registry_expect($request('GET', ['THEBEST_WORKFLOW_CATALOG' => 'relative.json'])['status'] === 503, 'Relative catalog paths must fail');
    $envelope = json_decode($raw, true, 64, JSON_THROW_ON_ERROR);
    $envelope['payload_b64'] = base64_encode(str_replace('Synthetic poster', 'Modified poster', base64_decode($envelope['payload_b64'], true)));
    file_put_contents($temporary, json_encode($envelope, JSON_THROW_ON_ERROR));
    registry_expect($request('GET')['status'] === 503, 'Payload tampering must fail before serving');
    $envelope = json_decode($raw, true, 64, JSON_THROW_ON_ERROR);
    $envelope['signature_b64'] .= "\n";
    file_put_contents($temporary, json_encode($envelope, JSON_THROW_ON_ERROR));
    registry_expect($request('GET')['status'] === 503, 'Noncanonical base64 must fail');
    $envelope = json_decode($raw, true, 64, JSON_THROW_ON_ERROR);
    $duplicatedEnvelope = '{"payload_b64":' . json_encode($envelope['payload_b64']) . ',"payload_b64":' . json_encode($envelope['payload_b64']) . ',"signature_b64":' . json_encode($envelope['signature_b64']) . '}';
    file_put_contents($temporary, $duplicatedEnvelope);
    registry_expect($request('GET')['status'] === 503, 'Duplicate envelope keys must fail');
    foreach (['"revision":1,"revision":1', '"revision":1,"\\u0072evision":1'] as $duplicate) {
        $payload = str_replace('"revision":1', $duplicate, json_encode($catalog, JSON_THROW_ON_ERROR));
        file_put_contents($temporary, json_encode([
            'payload_b64' => base64_encode($payload),
            'signature_b64' => base64_encode(sodium_crypto_sign_detached($payload, $secret)),
        ], JSON_THROW_ON_ERROR));
        registry_expect($request('GET')['status'] === 503, 'Duplicate decoded payload keys must fail even with a valid signature');
    }
    file_put_contents($temporary, str_repeat('x', THEBEST_WORKFLOW_CATALOG_MAX_BYTES + 1));
    registry_expect($request('GET')['status'] === 503, 'Oversized catalog must fail without returning its contents');
    file_put_contents($temporary, '{broken');
    registry_expect($request('GET')['status'] === 503, 'Malformed JSON must fail');
    $copy = $catalog; $copy['expires_at'] = gmdate('Y-m-d\TH:i:s\Z', $now); $reject($copy, 'Expired catalog must fail');
    $copy = $catalog; $copy['generated_at'] = gmdate('Y-m-d\TH:i:s\Z', $now + 301); $reject($copy, 'Future-generated catalog must fail');
    $copy = $catalog; $copy['generated_at'] = '2026-02-31T00:00:00Z'; $reject($copy, 'Invalid calendar dates must fail');
    $copy = $catalog; $copy['revision'] = 0; $reject($copy, 'Nonpositive revision must fail');
    $copy = $catalog; $copy['schema_version'] = 'unknown/v1'; $reject($copy, 'Unknown catalog schema must fail');
    $copy = $catalog; $copy['extra'] = true; $reject($copy, 'Unknown payload keys must fail');
    $copy = $catalog; $copy['workflows'] = [$entry, $entry]; $reject($copy, 'Duplicate workflow versions must fail');
    $copy = $catalog; $copy['workflows'] = array_fill(0, 501, $entry); $reject($copy, 'Excessive entry counts must fail');
    $copy = $catalog; $copy['workflows'][0]['sha256'] = str_repeat('0', 64); $reject($copy, 'CID/digest mismatch must fail');
    $copy = $catalog; $copy['workflows'][0]['size_bytes'] = 1000001; $reject($copy, 'Oversized workflow declaration must fail');
    $copy = $catalog; $copy['workflows'][0]['version'] = '01.0.0'; $reject($copy, 'Invalid SemVer must fail');
    $copy = $catalog; $copy['workflows'][0]['verification']['level'] = 'production'; $reject($copy, 'Unsupported verification labels must fail');
    $copy = $catalog; $copy['workflows'][0]['runtime_version'] = '999.0.0'; $reject($copy, 'Unsupported runtime must fail');
    $copy = $catalog; $copy['workflows'][0]['compatibility'] = ['windows']; $reject($copy, 'Compatibility must be a string map');
    $copy = $catalog; $copy['workflows'][0]['title'] = str_repeat("\u{00E9}", 200);
    file_put_contents($temporary, $sign($copy));
    registry_expect($request('GET')['status'] === 200, 'Text limits must count Unicode code points like the client');
    file_put_contents($temporary, $raw);
    $_GET = ['application' => 'unrelated'];
    registry_expect($request('GET')['body'] === $raw, 'Query filtering must not mutate signed contents');
    echo json_encode(['ok' => true, 'checks' => $checks, 'liveActivation' => false], JSON_PRETTY_PRINT) . PHP_EOL;
} finally {
    @unlink($temporary);
    sodium_memzero($secret);
    sodium_memzero($pair);
}
