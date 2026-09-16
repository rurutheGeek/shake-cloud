<?php
declare(strict_types=1);

/**
 * SharedFeeds — 全ユーザーの購読フィードを1つの共通タイムラインにする。
 *
 * FreshRSS は購読リストをユーザーごとに持つ。このシステム拡張は、誰かが
 * フィードを追加・削除したときに、同じリクエスト内で他の全ユーザーへ
 * 複製・削除する。追加のタイマーや外部ファイル編集は使わない。
 *
 * 既読・未読はユーザーごとの DB に残る。共有するのは購読リストだけ。
 * 利用するのは FreshRSS 標準の拡張フックと、ユーザー名を受け取れる DAO。
 *   - FeedBeforeInsert : 追加時に同報（app/Controllers/feedController.php）
 *   - ActionExecute    : 削除時に同報（lib/Minz/Dispatcher.php）
 *   - FreshrssInit     : 初回ログインのユーザーへ既存分を配る
 *
 * 失敗してもユーザー自身の操作は止めない（警告ログを出して継続する）。
 */
final class SharedFeedsExtension extends Minz_Extension {

	#[\Override]
	public function init(): void {
		parent::init();
		$this->registerHook(Minz_HookType::FeedBeforeInsert, [$this, 'shareAddedFeed']);
		$this->registerHook(Minz_HookType::ActionExecute, [$this, 'shareDeletedFeed']);
		$this->registerHook(Minz_HookType::FreshrssInit, [$this, 'catchUpCurrentUser']);
	}

	/**
	 * 現在のユーザー以外で、DB を読めるユーザー名を返す。
	 * SQLite では db.sqlite がまだ無いユーザーを触るとクエリが失敗するため、
	 * 存在するものだけを対象にする。
	 *
	 * @return list<string>
	 */
	private function otherUsers(): array {
		$current = Minz_User::name();
		$sqlite = (FreshRSS_Context::systemConf()->db['type'] ?? '') === 'sqlite';
		$users = [];
		foreach (FreshRSS_user_Controller::listUsers() as $user) {
			if ($user === $current) {
				continue;
			}
			if ($sqlite && !is_file(join_path(DATA_PATH, 'users', $user, 'db.sqlite'))) {
				continue;
			}
			$users[] = $user;
		}
		return $users;
	}

	/** 追加されたフィードを他の全ユーザーへその場で複製する。 */
	public function shareAddedFeed(FreshRSS_Feed $feed): FreshRSS_Feed {
		$current = Minz_User::name();
		try {
			if ($current !== null && $current !== '' && $current !== Minz_User::INTERNAL_USER) {
				foreach ($this->otherUsers() as $user) {
					$this->replicateTo($user, $current, $feed);
				}
			}
		} catch (Throwable $error) {
			Minz_Log::warning('[SharedFeeds] add sync failed: ' . $error->getMessage());
		}
		return $feed;
	}

	/**
	 * フィード削除の直前に、同じ URL を他の全ユーザーからも消す。
	 * ActionExecute は削除アクションの前に呼ばれるので、まだ URL を読める。
	 * true を返して本来の削除を続行させる。
	 */
	public function shareDeletedFeed(Minz_ActionController $controller): bool {
		if (!Minz_Request::is('feed', 'delete')) {
			return true;
		}
		try {
			$id = Minz_Request::paramInt('id');
			if ($id > 0) {
				$feed = FreshRSS_Factory::createFeedDao()->searchById($id);
				if ($feed !== null) {
					foreach ($this->otherUsers() as $user) {
						$this->removeFrom($user, $feed->url());
					}
				}
			}
		} catch (Throwable $error) {
			Minz_Log::warning('[SharedFeeds] delete sync failed: ' . $error->getMessage());
		}
		return true;
	}

	/**
	 * 現在のユーザーに、他のユーザーが持つフィードで足りないものを足す。
	 * 追加はフックで即時反映されるが、取りこぼし（同時書き込みの失敗、配備前
	 * から居たユーザー、API経由の解除の後始末）を毎リクエストで回復する。
	 * 既存フィードは触らない（削除やカテゴリ移動はしない）。
	 */
	public function catchUpCurrentUser(): void {
		$current = Minz_User::name();
		if ($current === null || $current === '' || $current === Minz_User::INTERNAL_USER) {
			return;
		}
		try {
			foreach ($this->otherUsers() as $user) {
				$feedDAO = FreshRSS_Factory::createFeedDao($user);
				foreach ($feedDAO->listFeeds() as $feed) {
					$this->replicateTo($current, $user, $feed);
				}
			}
		} catch (Throwable $error) {
			Minz_Log::warning('[SharedFeeds] catch-up failed: ' . $error->getMessage());
		}
	}

	/**
	 * source を target ユーザーの購読へ複製する。既に同じ URL があれば何もしない。
	 * カテゴリ名は source 側のカテゴリから引き継ぎ、無ければ target 側で作り、
	 * それもできなければ未分類へ入れる。
	 */
	private function replicateTo(string $target, string $sourceUser, FreshRSS_Feed $source): void {
		$url = $source->url();
		if ($url === '') {
			return;
		}
		try {
			$feedDAO = FreshRSS_Factory::createFeedDao($target);
			if ($feedDAO->searchByUrl($url) !== null) {
				return;
			}
			$categoryDAO = FreshRSS_Factory::createCategoryDao($target);
			$replica = new FreshRSS_Feed($url, false);
			$replica->_kind($source->kind());
			$replica->_attributes($source->attributes());
			if ($source->httpAuth() !== '') {
				$replica->_httpAuth($source->httpAuth());
			}
			$name = $source->name();
			if ($name !== '' && $name !== $url) {
				$replica->_name($name);
			}
			if ($source->website() !== '') {
				$replica->_website($source->website(), false);
			}
			if ($source->description() !== '') {
				$replica->_description($source->description());
			}
			$category = $this->resolveCategory($categoryDAO, $sourceUser, $source->categoryId());
			if ($category !== null) {
				$replica->_category($category);
			} else {
				$replica->_categoryId(FreshRSS_CategoryDAO::DEFAULTCATEGORYID);
			}
			$feedDAO->addFeedObject($replica);
		} catch (Throwable $error) {
			Minz_Log::warning('[SharedFeeds] cannot copy ' . $url . ' to ' . $target . ': ' . $error->getMessage());
		}
	}

	/** source 側のカテゴリ名を target 側で見つけるか作り、無ければ未分類にする。 */
	private function resolveCategory(FreshRSS_CategoryDAO $categoryDAO, string $sourceUser,
			int $sourceCategoryId): ?FreshRSS_Category {
		$categoryName = '';
		if ($sourceCategoryId > 0) {
			try {
				$sourceCategory = FreshRSS_Factory::createCategoryDao($sourceUser)->searchById($sourceCategoryId);
				if ($sourceCategory !== null) {
					$categoryName = $sourceCategory->name();
				}
			} catch (Throwable $error) {
				$categoryName = '';
			}
		}
		if ($categoryName !== '' && $categoryName !== FreshRSS_CategoryDAO::DEFAULT_CATEGORY_NAME) {
			$category = $categoryDAO->searchByName($categoryName);
			if ($category === null) {
				$id = $categoryDAO->addCategory(['name' => $categoryName]);
				if ($id) {
					$category = $categoryDAO->searchById($id);
				}
			}
			if ($category !== null) {
				return $category;
			}
		}
		$categoryDAO->checkDefault();
		return $categoryDAO->searchById(FreshRSS_CategoryDAO::DEFAULTCATEGORYID);
	}

	/** user の購読から URL のフィードを消す。 */
	private function removeFrom(string $user, string $url): void {
		try {
			$feedDAO = FreshRSS_Factory::createFeedDao($user);
			$feed = $feedDAO->searchByUrl($url);
			if ($feed !== null) {
				$feedDAO->deleteFeed($feed->id());
			}
		} catch (Throwable $error) {
			Minz_Log::warning('[SharedFeeds] cannot remove ' . $url . ' from ' . $user . ': ' . $error->getMessage());
		}
	}
}
