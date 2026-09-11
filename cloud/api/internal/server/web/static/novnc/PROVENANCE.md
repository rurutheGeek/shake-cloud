# noVNC vendor drop

- Version: noVNC 1.7.0 (`@novnc/novnc`)
- Source: https://registry.npmjs.org/@novnc/novnc/-/novnc-1.7.0.tgz
- npm integrity (sha512, base64): `ucEJOx4T2avIRCleodk7YobZj5O2Ga2AeLfQ69A/yjG9HHba2+PDgwSkN3FttrmG+70ZGx21sElNFouK13RzyA==`
- `core/`, `vendor/` and `LICENSE.txt` in this directory are copied unmodified from the
  tarball's `package/core/`, `package/vendor/` and `package/LICENSE.txt`. No app UI,
  build tooling, or other paths from the tarball are included.
- License: MPL-2.0 (see `LICENSE.txt`).

## Updating

1. Download the new tarball: `https://registry.npmjs.org/@novnc/novnc/-/novnc-<version>.tgz`.
2. Verify its npm integrity hash (`npm view @novnc/novnc@<version> dist.integrity`, or check
   against the published `package-lock.json`/registry metadata) against the downloaded file:
   `openssl dgst -sha512 -binary novnc-<version>.tgz | base64`.
3. Replace `core/`, `vendor/` and `LICENSE.txt` in this directory with the new tarball's
   `package/core/`, `package/vendor/` and `package/LICENSE.txt`, unmodified.
4. Update this file with the new version, URL, and integrity hash.
