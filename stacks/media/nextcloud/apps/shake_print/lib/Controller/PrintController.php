<?php

declare(strict_types=1);

namespace OCA\ShakePrint\Controller;

use OCP\AppFramework\Controller;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\Attribute\FrontpageRoute;
use OCP\AppFramework\Http\DataResponse;
use OCP\Files\File;
use OCP\Files\IRootFolder;
use OCP\Http\Client\IClientService;
use OCP\IConfig;
use OCP\IRequest;
use Psr\Log\LoggerInterface;

class PrintController extends Controller {
	/** CUPS がそのまま扱える形式だけ通す。 */
	private const ALLOWED_EXTENSIONS = ['pdf', 'png', 'jpg', 'jpeg', 'txt'];

	public function __construct(
		string $appName,
		IRequest $request,
		private IRootFolder $rootFolder,
		private IClientService $clientService,
		private IConfig $config,
		private LoggerInterface $logger,
		private ?string $userId,
	) {
		parent::__construct($appName, $request);
	}

	#[FrontpageRoute(verb: 'POST', url: '/print')]
	public function print(int $fileId, int $copies = 1, string $color = 'color'): DataResponse {
		if ($this->userId === null) {
			return new DataResponse(['error' => '認証が必要です'], Http::STATUS_UNAUTHORIZED);
		}

		$node = $this->findFile($fileId);
		if ($node === null) {
			return new DataResponse(['error' => 'ファイルが見つかりません'], Http::STATUS_NOT_FOUND);
		}
		if (!$node->isReadable()) {
			return new DataResponse(['error' => 'このファイルを読む権限がありません'], Http::STATUS_FORBIDDEN);
		}

		$extension = strtolower($node->getExtension());
		if (!in_array($extension, self::ALLOWED_EXTENSIONS, true)) {
			return new DataResponse(
				['error' => '印刷できる形式は PDF・PNG・JPEG・テキストです'],
				Http::STATUS_UNSUPPORTED_MEDIA_TYPE
			);
		}

		$url = rtrim($this->config->getAppValue('shake_print', 'print_api_url', ''), '/');
		$token = $this->config->getAppValue('shake_print', 'print_api_token', '');
		if ($url === '' || $token === '') {
			return new DataResponse(['error' => '印刷APIが設定されていません'], Http::STATUS_SERVICE_UNAVAILABLE);
		}

		$handle = $node->fopen('r');
		if ($handle === false) {
			return new DataResponse(['error' => 'ファイルを開けません'], Http::STATUS_INTERNAL_SERVER_ERROR);
		}

		try {
			$response = $this->clientService->newClient()->post($url . '/print', [
				'headers' => [
					'Authorization' => 'Bearer ' . $token,
					'Content-Type' => 'application/octet-stream',
					'X-Print-Filename' => rawurlencode($node->getName()),
					'X-Print-Copies' => (string) max(1, min(99, $copies)),
					'X-Print-Color' => $color === 'monochrome' ? 'monochrome' : 'color',
				],
				'body' => $handle,
				'timeout' => 60,
				'nextcloud' => ['allow_local_address' => true],
			]);
		} catch (\Throwable $error) {
			$this->logger->error('shake_print: relay request failed', ['exception' => $error]);
			return new DataResponse(['error' => '印刷中継に接続できません'], Http::STATUS_BAD_GATEWAY);
		} finally {
			if (is_resource($handle)) {
				fclose($handle);
			}
		}

		$result = json_decode((string)$response->getBody(), true);
		if (!is_array($result) || !isset($result['job'])) {
			return new DataResponse(['error' => '印刷ジョブを確認できません'], Http::STATUS_BAD_GATEWAY);
		}

		return new DataResponse(['job' => (string)$result['job']]);
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
