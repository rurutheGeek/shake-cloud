<?php

declare(strict_types=1);

namespace OCA\ShakeTags\Controller;

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

class TagsController extends Controller {
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

	#[FrontpageRoute(verb: 'GET', url: '/tags')]
	public function read(int $fileId): DataResponse {
		$relative = $this->libraryPath($fileId);
		if ($relative === null) {
			return $this->notInLibrary();
		}
		return $this->relay('get', '/tags', ['query' => ['path' => $relative]]);
	}

	#[FrontpageRoute(verb: 'POST', url: '/tags')]
	public function write(int $fileId, array $tags = []): DataResponse {
		$relative = $this->libraryPath($fileId);
		if ($relative === null) {
			return $this->notInLibrary();
		}
		return $this->relay('post', '/tags', [
			'json' => ['path' => $relative, 'tags' => $tags],
			'timeout' => 60,
		]);
	}

	#[FrontpageRoute(verb: 'GET', url: '/search')]
	public function search(string $artist = '', string $title = '', string $album = ''): DataResponse {
		return $this->relay('get', '/musicbrainz', [
			'query' => ['artist' => $artist, 'title' => $title, 'album' => $album],
			'timeout' => 30,
		]);
	}

	private function relay(string $method, string $path, array $options): DataResponse {
		$base = rtrim($this->config->getAppValue('shake_tags', 'tags_api_url', ''), '/');
		$token = $this->config->getAppValue('shake_tags', 'tags_api_token', '');
		if ($base === '' || $token === '') {
			return new DataResponse(['error' => 'タグAPIが設定されていません'],
				Http::STATUS_SERVICE_UNAVAILABLE);
		}
		$options['headers'] = ['Authorization' => 'Bearer ' . $token];
		$options['nextcloud'] = ['allow_local_address' => true];
		try {
			$client = $this->clientService->newClient();
			$response = $method === 'post'
				? $client->post($base . $path, $options)
				: $client->get($base . $path, $options);
			$payload = json_decode((string)$response->getBody(), true);
		} catch (\Throwable $error) {
			$this->logger->error('shake_tags: relay request failed', ['exception' => $error]);
			$message = 'タグAPIに接続できません（media-01の状態を確認してください）';
			if (method_exists($error, 'getResponse') && $error->getResponse() !== null) {
				$body = json_decode((string)$error->getResponse()->getBody(), true);
				if (is_array($body) && isset($body['error'])) {
					$message = (string)$body['error'];
				}
			}
			return new DataResponse(['error' => $message], Http::STATUS_BAD_GATEWAY);
		}
		if (!is_array($payload)) {
			return new DataResponse(['error' => 'タグAPIの応答を読めません'], Http::STATUS_BAD_GATEWAY);
		}
		return new DataResponse($payload);
	}

	private function libraryPath(int $fileId): ?string {
		if ($this->userId === null) {
			return null;
		}
		$folder = $this->rootFolder->getUserFolder($this->userId);
		$mount = $this->config->getAppValue('shake_tags', 'music_mount', 'music');
		$prefix = rtrim($folder->getPath(), '/') . '/' . trim($mount, '/') . '/';
		foreach ($folder->getById($fileId) as $node) {
			if (!($node instanceof File)) {
				continue;
			}
			$path = $node->getPath();
			if (!str_starts_with($path, $prefix)) {
				continue;
			}
			return substr($path, strlen($prefix));
		}
		return null;
	}

	private function notInLibrary(): DataResponse {
		return new DataResponse(
			['error' => 'musicライブラリのMP3を選んでください'],
			Http::STATUS_UNSUPPORTED_MEDIA_TYPE
		);
	}
}
