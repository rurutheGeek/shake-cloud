// tools/render-service-map.py が platform/terraform/dns.yaml と
// stacks/docs/service-map.yaml から書く。直接直さない。
window.SERVICE_MAP = {
 "edge": "core-01",
 "vms": [
  {
   "address": "192.168.10.1",
   "docs": [
    {
     "path": "operations/router/",
     "title": "router-01（OpenWrt・自作ルータ）"
    }
   ],
   "kind": "base",
   "name": "router-01",
   "role": "ルーター・DNS・VPN",
   "services": [
    {
     "description": "家庭内ルーター（WAN・LAN・DHCP）",
     "docs": [
      {
       "path": "operations/router/",
       "title": "router-01（OpenWrt・自作ルータ）"
      },
      {
       "path": "operations/router-config/",
       "title": "router-01 の設定まとめ（素の OpenWrt からの変更）"
      }
     ],
     "name": "OpenWrt"
    },
    {
     "description": "宅外から管理LANへ入る復旧経路",
     "docs": [
      {
       "path": "operations/net/",
       "title": "Tailscale（router-01 上の subnet router）"
      }
     ],
     "name": "Tailscale"
    },
    {
     "description": "DNS・広告遮断。Forward Auth",
     "docs": [
      {
       "path": "operations/adguard/",
       "title": "DNS と広告遮断（AdGuard Home）"
      }
     ],
     "name": "AdGuard Home",
     "route": [
      "core-01",
      "router-01"
     ],
     "sso": true,
     "upstream": "192.168.10.1:3000",
     "url": "https://adguard.apextox.dpdns.org/"
    },
    {
     "description": "LuCI。SSOなし・復旧経路",
     "docs": [
      {
       "path": "operations/router/",
       "title": "router-01（OpenWrt・自作ルータ）"
      }
     ],
     "name": "router-01 の管理画面",
     "route": [
      "core-01",
      "router-01"
     ],
     "sso": false,
     "upstream": "192.168.10.1:80",
     "url": "https://router.apextox.dpdns.org/"
    }
   ]
  },
  {
   "address": "192.168.10.200",
   "docs": [
    {
     "path": "operations/identity/",
     "title": "認証基盤（identity サービス・Authentik）"
    },
    {
     "path": "operations/edge/",
     "title": "HTTPSの入口を1台にまとめる"
    }
   ],
   "kind": "base",
   "name": "core-01",
   "role": "共通ログイン・台帳・HTTPSの入口",
   "services": [
    {
     "description": "すべての HTTPS を受けて各VMへ中継する",
     "docs": [
      {
       "path": "operations/edge/",
       "title": "HTTPSの入口を1台にまとめる"
      }
     ],
     "name": "Caddy（入口）"
    },
    {
     "description": "共通ログイン",
     "docs": [
      {
       "path": "services/identity/",
       "title": "共通ログインの使い方"
      },
      {
       "path": "operations/identity/",
       "title": "認証基盤（identity サービス・Authentik）"
      }
     ],
     "name": "Authentik",
     "route": [
      "core-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:9000",
     "url": "https://auth.apextox.dpdns.org/"
    },
    {
     "description": "",
     "docs": [
      {
       "path": "operations/netbox/",
       "title": "NetBox の使い方（台帳）"
      }
     ],
     "name": "NetBox",
     "route": [
      "core-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:8000",
     "url": "https://netbox.apextox.dpdns.org/"
    }
   ]
  },
  {
   "address": "192.168.10.205",
   "docs": [
    {
     "path": "operations/cloud/",
     "title": "クラウドAPIの構築"
    }
   ],
   "kind": "base",
   "name": "cloud-01",
   "role": "自作クラウド・S3",
   "services": [
    {
     "description": "S3互換オブジェクトストア",
     "docs": [
      {
       "path": "operations/garage/",
       "title": "Garage（S3互換オブジェクトストア）"
      }
     ],
     "name": "Garage"
    },
    {
     "description": "",
     "docs": [
      {
       "path": "services/cloud/",
       "title": "クラウドの使い方（ポータル・CLI・Terraform）"
      },
      {
       "path": "operations/cloud-api/",
       "title": "クラウドAPI本体とインスタンス"
      }
     ],
     "name": "クラウドのポータルとAPI",
     "route": [
      "core-01",
      "cloud-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:8080",
     "url": "https://cloud.apextox.dpdns.org/"
    }
   ]
  },
  {
   "address": "192.168.10.210",
   "docs": [
    {
     "path": "operations/monitoring/",
     "title": "監視（monitor-01）"
    }
   ],
   "kind": "base",
   "name": "monitor-01",
   "role": "監視",
   "services": [
    {
     "description": "メトリクスの収集とアラート",
     "docs": [
      {
       "path": "operations/monitoring/",
       "title": "監視（monitor-01）"
      }
     ],
     "name": "Prometheus"
    },
    {
     "description": "アラートの通知",
     "docs": [
      {
       "path": "operations/monitoring/",
       "title": "監視（monitor-01）"
      }
     ],
     "name": "Alertmanager"
    },
    {
     "description": "監視ポータル。OIDC",
     "docs": [
      {
       "path": "operations/monitoring/",
       "title": "監視（monitor-01）"
      }
     ],
     "name": "Grafana",
     "route": [
      "core-01",
      "monitor-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:3000",
     "url": "https://grafana.apextox.dpdns.org/"
    },
    {
     "description": "UPSのREST。HomarrのUPSウィジェット用",
     "docs": [
      {
       "path": "operations/power/",
       "title": "電源と UPS"
      }
     ],
     "name": "PeaNUT",
     "route": [
      "core-01",
      "monitor-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:8080",
     "url": "https://peanut.apextox.dpdns.org/"
    }
   ]
  },
  {
   "address": "192.168.10.105",
   "docs": [
    {
     "path": "operations/services/",
     "title": "サービスの置き場所とクラウドVMでの作り方"
    }
   ],
   "kind": "cloud",
   "name": "apps-01",
   "role": "入口のハブ・パスワード・家電",
   "services": [
    {
     "description": "Eufy カメラと Home Assistant の橋渡し",
     "docs": [
      {
       "path": "services/home-assistant/",
       "title": "Home Assistantと家電の使い方（利用者向け）"
      }
     ],
     "name": "eufy-security-ws"
    },
    {
     "description": "サービスの入口。OIDC",
     "docs": [
      {
       "path": "services/homarr/",
       "title": "Homarrの使い方"
      }
     ],
     "name": "Homarr",
     "route": [
      "core-01",
      "apps-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:7575",
     "url": "https://homarr.apextox.dpdns.org/"
    },
    {
     "description": "パスワード管理・SSO",
     "docs": [
      {
       "path": "operations/vaultwarden/",
       "title": "Vaultwarden"
      }
     ],
     "name": "Vaultwarden",
     "route": [
      "core-01",
      "apps-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:8222",
     "url": "https://vault.apextox.dpdns.org/"
    },
    {
     "description": "端末↔apps-01の速度計測",
     "docs": [
      {
       "path": "services/librespeed/",
       "title": "通信速度テスト（LibreSpeed）"
      }
     ],
     "name": "LibreSpeed",
     "route": [
      "core-01",
      "apps-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:8300",
     "url": "https://speed.apextox.dpdns.org/"
    },
    {
     "description": "翻訳サイトと拡張機能の配布",
     "docs": [
      {
       "path": "services/poke-translate/",
       "title": "ポケモン翻訳"
      }
     ],
     "name": "ポケモン用語対応翻訳",
     "route": [
      "core-01",
      "apps-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:8320",
     "url": "https://poke.apextox.dpdns.org/"
    },
    {
     "description": "家電・自動化",
     "docs": [
      {
       "path": "services/home-assistant/",
       "title": "Home Assistantと家電の使い方（利用者向け）"
      }
     ],
     "name": "Home Assistant",
     "route": [
      "core-01",
      "apps-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:8123",
     "url": "https://ha.apextox.dpdns.org/"
    },
    {
     "description": "",
     "docs": [
      {
       "path": "contributing-docs/",
       "title": "ドキュメントの書き方"
      }
     ],
     "name": "ドキュメントサイト",
     "route": [
      "core-01",
      "apps-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:8090",
     "url": "https://docs.apextox.dpdns.org/"
    },
    {
     "description": "ログ・再起動・manage.pyの定型操作。Forward Auth",
     "docs": [
      {
       "path": "operations/bot-portal/",
       "title": "Botポータル"
      }
     ],
     "name": "Botポータル",
     "route": [
      "core-01",
      "apps-01"
     ],
     "sso": true,
     "upstream": "127.0.0.1:8095",
     "url": "https://portal.apextox.dpdns.org/"
    },
    {
     "description": "apps-01・5432",
     "docs": [
      {
       "path": "operations/pkdb/",
       "title": "ポケモン系のPostgreSQL（pkdb）"
      }
     ],
     "name": "ポケモン系のPostgreSQL",
     "url": "https://pkdb.apextox.dpdns.org/"
    },
    {
     "description": "ポケモン系PostgreSQLの管理画面。Forward Auth・admins のみ",
     "docs": [
      {
       "path": "operations/pkdb/",
       "title": "ポケモン系のPostgreSQL（pkdb）"
      }
     ],
     "name": "Adminer",
     "route": [
      "core-01",
      "apps-01"
     ],
     "sso": true,
     "upstream": "127.0.0.1:8330",
     "url": "https://adminer.apextox.dpdns.org/"
    },
    {
     "description": "ポケモン系PostgreSQLへ新しいポケモンを足す画面。Forward Auth",
     "docs": [
      {
       "path": "operations/pkdb/",
       "title": "ポケモン系のPostgreSQL（pkdb）"
      }
     ],
     "name": "ポケモン登録",
     "route": [
      "core-01",
      "apps-01"
     ],
     "sso": true,
     "upstream": "127.0.0.1:8331",
     "url": "https://pkdb-entry.apextox.dpdns.org/"
    },
    {
     "description": "印刷状況。Forward Auth",
     "docs": [
      {
       "path": "services/printer/",
       "title": "プリンター（Canon TS8430シリーズ）"
      }
     ],
     "name": "CUPS",
     "route": [
      "core-01",
      "apps-01"
     ],
     "sso": true,
     "upstream": "192.168.10.105:631",
     "url": "https://cups.apextox.dpdns.org/"
    },
    {
     "description": "通知メールを読み取り専用で表示。Forward Auth",
     "docs": [
      {
       "path": "operations/smtp/",
       "title": "SMTPとメール送信"
      }
     ],
     "name": "Gmailビューア",
     "route": [
      "core-01",
      "apps-01"
     ],
     "sso": true,
     "upstream": "127.0.0.1:8310",
     "url": "https://mail-view.apextox.dpdns.org/"
    }
   ]
  },
  {
   "address": "192.168.10.101",
   "docs": [
    {
     "path": "operations/nextcloud/",
     "title": "Nextcloudと追加アプリ"
    },
    {
     "path": "operations/bulk-storage/",
     "title": "共有バルクストレージ（6TB USB HDD）"
    }
   ],
   "kind": "cloud",
   "name": "media-01",
   "role": "ファイル・本・音楽",
   "services": [
    {
     "description": "ファイル・カレンダー・タスク",
     "docs": [
      {
       "path": "services/nextcloud-guide/",
       "title": "Nextcloudの使い方（利用者向け）"
      },
      {
       "path": "operations/nextcloud/",
       "title": "Nextcloudと追加アプリ"
      }
     ],
     "name": "Nextcloud",
     "route": [
      "core-01",
      "media-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:8080",
     "url": "https://nextcloud.apextox.dpdns.org/"
    },
    {
     "description": "電子書籍リーダー",
     "docs": [
      {
       "path": "services/usage/",
       "title": "利用者向け：全サービスの使い方"
      }
     ],
     "name": "Kavita",
     "route": [
      "core-01",
      "media-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:5000",
     "url": "https://kavita.apextox.dpdns.org/"
    },
    {
     "description": "音楽ストリーミング。Forward Auth",
     "docs": [
      {
       "path": "services/music/",
       "title": "音楽の取り込み・タグ編集・BCSTM"
      }
     ],
     "name": "Navidrome",
     "route": [
      "core-01",
      "media-01"
     ],
     "sso": true,
     "upstream": "127.0.0.1:4533",
     "url": "https://navidrome.apextox.dpdns.org/"
    },
    {
     "description": "アプリ用・SSOなし",
     "docs": [
      {
       "path": "services/music/",
       "title": "音楽の取り込み・タグ編集・BCSTM"
      }
     ],
     "name": "Navidrome Subsonic API",
     "route": [
      "core-01",
      "media-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:4533",
     "url": "https://navidrome-api.apextox.dpdns.org/"
    },
    {
     "description": "読み書き・タグ・圧縮解凍。SSOなし・自前認証",
     "docs": [
      {
       "path": "services/nextcloud-agent/",
       "title": "Nextcloudファイルエージェント（AI用MCP）"
      },
      {
       "path": "operations/nextcloud-mcp/",
       "title": "Nextcloud MCPサーバ（管理者向け）"
      }
     ],
     "name": "NextcloudのAIエージェント用MCP",
     "route": [
      "core-01",
      "media-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:5811",
     "url": "https://nextcloud-mcp.apextox.dpdns.org/"
    },
    {
     "description": "UrBackupの状態と端末手順。Forward Auth",
     "docs": [
      {
       "path": "operations/client-backup/",
       "title": "クライアント端末のバックアップ（Windows・Android）"
      }
     ],
     "name": "バックアップポータル",
     "route": [
      "core-01",
      "media-01"
     ],
     "sso": true,
     "upstream": "127.0.0.1:55416",
     "url": "https://backup.apextox.dpdns.org/"
    },
    {
     "description": "配布・世代・復元。Forward Auth",
     "docs": [
      {
       "path": "operations/client-backup/",
       "title": "クライアント端末のバックアップ（Windows・Android）"
      }
     ],
     "name": "UrBackup管理画面",
     "route": [
      "core-01",
      "media-01"
     ],
     "sso": true,
     "upstream": "127.0.0.1:55414",
     "url": "https://urbackup.apextox.dpdns.org/"
    },
    {
     "description": "動画ダウンローダー。Forward Auth",
     "docs": [
      {
       "path": "services/usage/",
       "title": "利用者向け：全サービスの使い方"
      }
     ],
     "name": "MeTube",
     "route": [
      "core-01",
      "media-01"
     ],
     "sso": true,
     "upstream": "127.0.0.1:8081",
     "url": "https://metube.apextox.dpdns.org/"
    },
    {
     "description": "アルバム一括ダウンローダー。Forward Auth",
     "docs": [
      {
       "path": "services/music/",
       "title": "音楽の取り込み・タグ編集・BCSTM"
      }
     ],
     "name": "KHInsider",
     "route": [
      "core-01",
      "media-01"
     ],
     "sso": true,
     "upstream": "127.0.0.1:5820",
     "url": "https://khinsider.apextox.dpdns.org/"
    },
    {
     "description": "共通RSSタイムライン。OIDC",
     "docs": [
      {
       "path": "services/rss/",
       "title": "共通RSSタイムライン（FreshRSS）"
      }
     ],
     "name": "FreshRSS",
     "route": [
      "core-01",
      "media-01"
     ],
     "sso": false,
     "upstream": "127.0.0.1:8082",
     "url": "https://freshrss.apextox.dpdns.org/"
    },
    {
     "description": "media-01・53317",
     "docs": [
      {
       "path": "services/usage/",
       "title": "利用者向け：全サービスの使い方"
      }
     ],
     "name": "LocalSend受信機",
     "url": "https://localsend.apextox.dpdns.org/"
    }
   ]
  },
  {
   "address": "192.168.10.102",
   "docs": [
    {
     "path": "operations/web/",
     "title": "公開サイト（Shake-Web / pkhack / Alexa / ayahuya）"
    }
   ],
   "kind": "cloud",
   "name": "web-01",
   "role": "公開サイト",
   "services": [
    {
     "description": "Issues・Shaketter・ToBa・ikura と Wiki",
     "docs": [
      {
       "path": "operations/web/",
       "title": "公開サイト（Shake-Web / pkhack / Alexa / ayahuya）"
      }
     ],
     "name": "Shake-Web"
    },
    {
     "description": "ポケモンクイズ",
     "docs": [
      {
       "path": "operations/web/",
       "title": "公開サイト（Shake-Web / pkhack / Alexa / ayahuya）"
      }
     ],
     "name": "pkhack"
    },
    {
     "description": "4サイトの入口。CloudFlare Origin 証明書で TLS 終端",
     "docs": [
      {
       "path": "operations/web/",
       "title": "公開サイト（Shake-Web / pkhack / Alexa / ayahuya）"
      }
     ],
     "name": "nginx"
    }
   ]
  },
  {
   "address": "192.168.10.127",
   "docs": [
    {
     "path": "architecture/gaming/",
     "title": "ゲームと開発環境"
    }
   ],
   "kind": "cloud",
   "name": "game-01",
   "role": "ゲーム（GPUパススルー）",
   "services": [
    {
     "description": "ゲームのストリーミング",
     "docs": [
      {
       "path": "architecture/gaming/",
       "title": "ゲームと開発環境"
      }
     ],
     "name": "Wolf"
    },
    {
     "description": "ROM ライブラリ",
     "docs": [
      {
       "path": "architecture/gaming/",
       "title": "ゲームと開発環境"
      }
     ],
     "name": "RomM"
    }
   ]
  },
  {
   "address": "192.168.10.202 / .203",
   "docs": [
    {
     "path": "services/devvm/",
     "title": "開発VMの使い方"
    },
    {
     "path": "onboarding/",
     "title": "開発参加ガイド"
    }
   ],
   "kind": "cloud",
   "name": "dev-01 / dev-02",
   "role": "開発",
   "services": []
  },
  {
   "address": "192.168.10.100 / .104",
   "docs": [
    {
     "path": "operations/windows/",
     "title": "Windows 11 Pro の VM をポータルから作る"
    },
    {
     "path": "services/android/",
     "title": "Android VMの画面を使う（RDP）"
    }
   ],
   "kind": "cloud",
   "name": "win-01 / android-01",
   "role": "開発用の Windows・Android",
   "services": []
  },
  {
   "address": "192.168.10.220-",
   "docs": [
    {
     "path": "operations/kubernetes/",
     "title": "Kubernetes クラスタ"
    }
   ],
   "kind": "base",
   "name": "k8s（必要なときだけ起動）",
   "role": "AWX・DB・関数",
   "services": [
    {
     "description": "クラウドのデータベース",
     "docs": [
      {
       "path": "operations/cloud-resources/",
       "title": "ボリューム・S3・DB・関数"
      }
     ],
     "name": "CloudNativePG"
    },
    {
     "description": "クラウドの関数",
     "docs": [
      {
       "path": "operations/cloud-resources/",
       "title": "ボリューム・S3・DB・関数"
      }
     ],
     "name": "Knative"
    },
    {
     "description": "Kubernetes の Cilium Ingress。TLS は cert-manager",
     "docs": [
      {
       "path": "operations/awx/",
       "title": "AWX の使い方"
      }
     ],
     "name": "AWX",
     "url": "https://awx.apextox.dpdns.org/"
    },
    {
     "description": "Kourier の LoadBalancer",
     "docs": [],
     "name": "Knative の関数 URL"
    }
   ]
  },
  {
   "address": "192.168.10.10",
   "docs": [
    {
     "path": "operations/bootstrap/",
     "title": "初回セットアップの順番"
    },
    {
     "path": "operations/backup/",
     "title": "バックアップ（重要VM・game1セーブ）"
    }
   ],
   "kind": "host",
   "name": "apextox",
   "role": "Proxmox VE のホスト",
   "services": [
    {
     "description": "ポート8006",
     "docs": [
      {
       "path": "operations/bootstrap/",
       "title": "初回セットアップの順番"
      }
     ],
     "name": "Proxmoxの管理画面",
     "url": "https://pve.apextox.dpdns.org:8006/"
    }
   ]
  }
 ]
};
