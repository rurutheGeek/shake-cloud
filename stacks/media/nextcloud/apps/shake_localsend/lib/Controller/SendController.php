<?php

declare(strict_types=1);

namespace OCA\ShakeLocalSend\Controller;

use OCP\AppFramework\Controller;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\Attribute\FrontpageRoute;
use OCP\AppFramework\Http\DataResponse;
use OCP\Files\File;
use OCP\Files\IRootFolder;
use OCP\Http\Client\IClientService;
use OCP\IConfig;
use OCP\IRequest;
use OCP\IUserSession;
use Psr\Log\LoggerInterface;

class SendController extends Controller {
	public function __construct(
		string $appName,
		IRequest $request,
		private IRootFolder $rootFolder,
		private IClientService $clientService,
		private IConfig $config,
		private IUserSession $userSession,
		private LoggerInterface $logger,
		private ?string $userId,
	) {
		parent::__construct($appName, $request);
	}

	#[FrontpageRoute(verb: 'GET', url: '/devices')]
	public function devices(): DataResponse {
		if (!$this->configured()) {
			return new DataResponse(['error' => 'LocalSend送信APIが設定されていません'],
				Http::STATUS_SERVICE_UNAVAILABLE);
		}
		try {
			$response = $this->client()->get($this->baseUrl() . '/devices', [
				'headers' => $this->authHeaders(),
				'timeout' => 30,
			]);
			$payload = json_decode((string)$response->getBody(), true);
		} catch (\Throwable $error) {
			$this->logger->error('shake_localsend: device lookup failed', ['exception' => $error]);
			return new DataResponse(['error' => '端末一覧を取得できません（送信APIに接続できません）'],
				Http::STATUS_BAD_GATEWAY);
		}
		if (!is_array($payload) || !isset($payload['devices'])) {
			return new DataResponse(['error' => '端末一覧を読めません'], Http::STATUS_BAD_GATEWAY);
		}
		return new DataResponse(['devices' => $payload['devices']]);
	}

	#[FrontpageRoute(verb: 'POST', url: '/send')]
	public function send(int $fileId, string $fingerprint): DataResponse {
		if ($this->userId === null) {
			return new DataResponse(['error' => '認証が必要です'], Http::STATUS_UNAUTHORIZED);
		}
		if (!$this->configured()) {
			return new DataResponse(['error' => 'LocalSend送信APIが設定されていません'],
				Http::STATUS_SERVICE_UNAVAILABLE);
		}
		$node = $this->findFile($fileId);
		if ($node === null) {
			return new DataResponse(['error' => 'ファイルが見つかりません'], Http::STATUS_NOT_FOUND);
		}
		if (!$node->isReadable()) {
			return new DataResponse(['error' => 'このファイルを読む権限がありません'], Http::STATUS_FORBIDDEN);
		}
		$handle = $node->fopen('r');
		if ($handle === false) {
			return new DataResponse(['error' => 'ファイルを開けません'], Http::STATUS_INTERNAL_SERVER_ERROR);
		}
		$displayName = $this->userSession->getUser()?->getDisplayName() ?? '';

		try {
			$response = $this->client()->post($this->baseUrl() . '/send', [
				'headers' => $this->authHeaders() + [
					'Content-Type' => 'application/octet-stream',
					'X-Send-To' => $fingerprint,
					'X-Send-Filename' => rawurlencode($node->getName()),
					'X-Send-User' => rawurlencode($displayName),
				],
				'body' => $handle,
				'timeout' => 300,
				'nextcloud' => ['allow_local_address' => true],
			]);
		} catch (\Throwable $error) {
			$this->logger->error('shake_localsend: send failed', ['exception' => $error]);
			return new DataResponse(['error' => '送信に失敗しました（端末のLocalSendを開いて再試行してください）'],
				Http::STATUS_BAD_GATEWAY);
		} finally {
			if (is_resource($handle)) {
				fclose($handle);
			}
		}

		$result = json_decode((string)$response->getBody(), true);
		if (!is_array($result) || !isset($result['status'])) {
			return new DataResponse(['error' => '送信結果を確認できません'], Http::STATUS_BAD_GATEWAY);
		}
		return new DataResponse($result);
	}

	private function configured(): bool {
		return $this->config->getAppValue('shake_localsend', 'send_api_url', '') !== ''
			&& $this->config->getAppValue('shake_localsend', 'send_api_token', '') !== '';
	}

	private function baseUrl(): string {
		return rtrim($this->config->getAppValue('shake_localsend', 'send_api_url', ''), '/');
	}

	private function authHeaders(): array {
		return ['Authorization' => 'Bearer '
			. $this->config->getAppValue('shake_localsend', 'send_api_token', '')];
	}

	private function client() {
		return $this->clientService->newClient();
	}

	private function findFile(int $fileId): ?File {
		$folder = $this->rootFolder->getUserFolder($this->userId);
		foreach ($folder->getById($fileId) as $node) {
			if ($node instanceof File) {
				return $node;
			}
		}
		return null;
	}
}
