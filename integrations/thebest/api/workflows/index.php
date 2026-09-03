<?php
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 L1ght5p33d contributors
declare(strict_types=1);

require_once __DIR__ . '/_catalog.php';

$response = thebest_workflow_registry_response($_SERVER['REQUEST_METHOD'] ?? 'GET');
http_response_code($response['status']);
foreach ($response['headers'] as $name => $value) header($name . ': ' . $value);
echo $response['body'];
