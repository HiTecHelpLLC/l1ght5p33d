<?php
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 L1ght5p33d contributors
declare(strict_types=1);

/** Local operator-curated signed catalog. No upload, account or economy surface. */
const THEBEST_WORKFLOW_CATALOG_MAX_BYTES = 2000000;

/** Native syntax validation plus a bounded lexical check for duplicate keys. */
function thebest_workflow_catalog_decode(string $raw): mixed
{
    $decoded = json_decode($raw, false, 64, JSON_THROW_ON_ERROR);
    $frames = [];
    $length = strlen($raw);
    for ($position = 0; $position < $length; $position++) {
        $character = $raw[$position];
        if ($character === '{' || $character === '[') {
            $frames[] = ['object' => $character === '{', 'keys' => []];
        } elseif ($character === '}' || $character === ']') {
            array_pop($frames);
        } elseif ($character === '"') {
            $start = $position;
            // json_decode has already proved escape syntax and string closure.
            for ($position++; $position < $length; $position++) {
                if ($raw[$position] === '\\') $position++;
                elseif ($raw[$position] === '"') break;
            }
            $next = $position + 1;
            while ($next < $length && str_contains(" \r\n\t", $raw[$next])) $next++;
            if ($next < $length && $raw[$next] === ':') {
                $key = json_decode(substr($raw, $start, $position - $start + 1), false, 64, JSON_THROW_ON_ERROR);
                $frame = array_key_last($frames);
                if ($frame === null || !$frames[$frame]['object']) throw new RuntimeException('Invalid object key');
                // Prefix prevents numeric strings from becoming PHP integer keys.
                $key = '#' . $key;
                if (isset($frames[$frame]['keys'][$key])) throw new RuntimeException('Duplicate JSON key');
                $frames[$frame]['keys'][$key] = true;
            }
        }
    }
    return $decoded;
}

function thebest_workflow_registry_setting(string $name): string
{
    if (defined($name)) return (string) constant($name);
    $value = getenv($name);
    return $value === false ? '' : (string) $value;
}

function thebest_workflow_catalog_keys(stdClass $value, array $expected): void
{
    $actual = array_keys(get_object_vars($value));
    sort($actual);
    sort($expected);
    if ($actual !== $expected) throw new RuntimeException('Invalid catalog fields');
}

function thebest_workflow_catalog_text(mixed $value, int $minimum, int $maximum): void
{
    $length = is_string($value) ? preg_match_all('/./us', $value) : false;
    if ($length === false || $length < $minimum || $length > $maximum) {
        throw new RuntimeException('Invalid catalog text');
    }
}

function thebest_workflow_catalog_base64(mixed $encoded, int $maximum): string
{
    if (!is_string($encoded) || strlen($encoded) > $maximum) throw new RuntimeException('Invalid base64');
    $decoded = base64_decode($encoded, true);
    if ($decoded === false || base64_encode($decoded) !== $encoded) throw new RuntimeException('Invalid base64');
    return $decoded;
}

function thebest_workflow_catalog_time(mixed $value): float
{
    if (!is_string($value) || !preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/D', $value)) {
        throw new RuntimeException('Invalid UTC timestamp');
    }
    $date = new DateTimeImmutable($value);
    if ($date->format('Y-m-d\TH:i:s') !== substr($value, 0, 19)) throw new RuntimeException('Invalid calendar date');
    return (float) $date->format('U.u');
}

function thebest_workflow_catalog_cid(string $sha256): string
{
    // CIDv1 + raw codec + sha2-256 multihash, encoded as lowercase base32.
    $bytes = hex2bin('01551220' . $sha256);
    if ($bytes === false) throw new RuntimeException('Invalid digest');
    $alphabet = 'abcdefghijklmnopqrstuvwxyz234567';
    $buffer = 0;
    $bits = 0;
    $result = 'b';
    foreach (unpack('C*', $bytes) as $byte) {
        $buffer = ($buffer << 8) | $byte;
        $bits += 8;
        while ($bits >= 5) {
            $bits -= 5;
            $result .= $alphabet[($buffer >> $bits) & 31];
        }
        $buffer &= (1 << $bits) - 1;
    }
    if ($bits > 0) $result .= $alphabet[($buffer << (5 - $bits)) & 31];
    return $result;
}

function thebest_workflow_catalog_validate(string $raw, string $publicKeyHex, int $now): void
{
    if (!function_exists('sodium_crypto_sign_verify_detached') || !preg_match('/^[0-9a-fA-F]{64}$/D', $publicKeyHex)) {
        throw new RuntimeException('Catalog signature verification unavailable');
    }
    if (strlen($raw) > THEBEST_WORKFLOW_CATALOG_MAX_BYTES) throw new RuntimeException('Catalog too large');
    $envelope = thebest_workflow_catalog_decode($raw);
    if (!$envelope instanceof stdClass) throw new RuntimeException('Invalid catalog envelope');
    thebest_workflow_catalog_keys($envelope, ['payload_b64', 'signature_b64']);
    $payload = thebest_workflow_catalog_base64($envelope->payload_b64, THEBEST_WORKFLOW_CATALOG_MAX_BYTES);
    $signature = thebest_workflow_catalog_base64($envelope->signature_b64, 88);
    if (strlen($signature) !== 64 || !sodium_crypto_sign_verify_detached($signature, $payload, hex2bin($publicKeyHex))) {
        throw new RuntimeException('Invalid catalog signature');
    }
    if (preg_match('/[^\x00-\x7F]/', $payload)) throw new RuntimeException('Catalog payload must be ASCII JSON');
    $catalog = thebest_workflow_catalog_decode($payload);
    if (!$catalog instanceof stdClass) throw new RuntimeException('Invalid catalog payload');
    thebest_workflow_catalog_keys($catalog, ['schema_version', 'revision', 'generated_at', 'expires_at', 'workflows']);
    if ($catalog->schema_version !== 'l1ght5p33d-catalog/v1' || !is_int($catalog->revision) || $catalog->revision < 1) {
        throw new RuntimeException('Invalid catalog version');
    }
    $generated = thebest_workflow_catalog_time($catalog->generated_at);
    $expires = thebest_workflow_catalog_time($catalog->expires_at);
    if ($expires <= $now || $expires <= $generated || $generated > $now + 300) throw new RuntimeException('Invalid catalog validity interval');
    if (!is_array($catalog->workflows) || count($catalog->workflows) > 500) throw new RuntimeException('Invalid catalog entries');
    $identities = [];
    foreach ($catalog->workflows as $entry) {
        if (!$entry instanceof stdClass) throw new RuntimeException('Invalid workflow entry');
        thebest_workflow_catalog_keys($entry, ['id', 'version', 'title', 'description', 'application', 'workflow_schema', 'runtime_version', 'license', 'cid', 'sha256', 'size_bytes', 'compatibility', 'verification']);
        foreach (['id', 'application'] as $field) {
            if (!is_string($entry->$field) || !preg_match('/^[a-z][a-z0-9_-]{0,63}$/D', $entry->$field)) throw new RuntimeException('Invalid workflow identifier');
        }
        thebest_workflow_catalog_text($entry->version, 1, 80);
        if (!preg_match('/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?$/D', $entry->version)) throw new RuntimeException('Invalid semantic version');
        thebest_workflow_catalog_text($entry->title, 1, 200);
        thebest_workflow_catalog_text($entry->description, 0, 4000);
        thebest_workflow_catalog_text($entry->license, 1, 100);
        if ($entry->workflow_schema !== 'l1ght5p33d/v1' || $entry->runtime_version !== '1.34.0') throw new RuntimeException('Unsupported workflow runtime');
        if (!is_string($entry->sha256) || !preg_match('/^[0-9a-f]{64}$/D', $entry->sha256)) throw new RuntimeException('Invalid workflow digest');
        if (!is_string($entry->cid) || !hash_equals(thebest_workflow_catalog_cid($entry->sha256), $entry->cid)) throw new RuntimeException('CID does not match the workflow digest');
        if (!is_int($entry->size_bytes) || $entry->size_bytes < 1 || $entry->size_bytes > 1000000) throw new RuntimeException('Invalid workflow size');
        if (!$entry->compatibility instanceof stdClass || count(get_object_vars($entry->compatibility)) > 32) throw new RuntimeException('Invalid compatibility declarations');
        foreach (get_object_vars($entry->compatibility) as $key => $value) {
            thebest_workflow_catalog_text((string) $key, 1, 64);
            thebest_workflow_catalog_text($value, 0, 200);
        }
        if (!$entry->verification instanceof stdClass) throw new RuntimeException('Invalid verification declaration');
        thebest_workflow_catalog_keys($entry->verification, ['level', 'description']);
        if (!in_array($entry->verification->level, ['fixture', 'local', 'live'], true)) throw new RuntimeException('Invalid verification level');
        thebest_workflow_catalog_text($entry->verification->description, 1, 4000);
        $identity = $entry->id . '@' . $entry->version;
        if (isset($identities[$identity])) throw new RuntimeException('Duplicate workflow version');
        $identities[$identity] = true;
    }
}

/** Pure response construction keeps tests independent of database/accounts. */
function thebest_workflow_registry_response(string $method, array $settings = [], ?string $webRoot = null, ?int $now = null): array
{
    $setting = static fn(string $name): string => array_key_exists($name, $settings) ? (string) $settings[$name] : thebest_workflow_registry_setting($name);
    $headers = ['Content-Type' => 'application/json; charset=utf-8', 'Cache-Control' => 'no-store', 'X-Content-Type-Options' => 'nosniff'];
    $status = 404;
    $body = '{"error":"not_found"}';
    if (in_array(strtolower(trim($setting('THEBEST_WORKFLOW_REGISTRY_ENABLED'))), ['1', 'true'], true)) {
        if (!in_array($method, ['GET', 'HEAD'], true)) {
            $status = 405;
            $headers['Allow'] = 'GET, HEAD';
            $body = '{"error":"method_not_allowed"}';
        } else {
            try {
                $configured = $setting('THEBEST_WORKFLOW_CATALOG');
                if (str_contains($configured, '://') || !preg_match('#^(?:/|[a-zA-Z]:[\\\\/])#', $configured)) throw new RuntimeException('Catalog must be a private absolute local path');
                $path = realpath($configured);
                $root = realpath($webRoot ?? dirname(__DIR__, 2));
                if ($path === false || $root === false || !is_file($path)) throw new RuntimeException('Catalog unavailable');
                $normalPath = str_replace('\\', '/', $path);
                $normalRoot = rtrim(str_replace('\\', '/', $root), '/');
                if (PHP_OS_FAMILY === 'Windows') {
                    $normalPath = strtolower($normalPath);
                    $normalRoot = strtolower($normalRoot);
                }
                if ($normalPath === $normalRoot || str_starts_with($normalPath, $normalRoot . '/')) throw new RuntimeException('Catalog must remain outside the web root');
                $handle = @fopen($path, 'rb');
                if ($handle === false) throw new RuntimeException('Catalog unavailable');
                try {
                    $raw = stream_get_contents($handle, THEBEST_WORKFLOW_CATALOG_MAX_BYTES + 1);
                } finally {
                    fclose($handle);
                }
                if ($raw === false) throw new RuntimeException('Catalog unavailable');
                thebest_workflow_catalog_validate($raw, $setting('THEBEST_WORKFLOW_REGISTRY_PUBLIC_KEY'), $now ?? time());
                $status = 200;
                $body = $raw; // Serve the exact signed envelope; never filter or re-encode it.
            } catch (Throwable $error) {
                $status = 503;
                $body = '{"error":"registry_unavailable"}';
            }
        }
    }
    $headers['Content-Length'] = (string) strlen($body);
    return ['status' => $status, 'headers' => $headers, 'body' => $method === 'HEAD' ? '' : $body];
}
