import { FileAction, FileType, registerFileAction } from '@nextcloud/files'
import { translate as t } from '@nextcloud/l10n'
import { generateUrl } from '@nextcloud/router'
import axios from '@nextcloud/axios'

const toast = (method, message) => {
	if (window.OCP?.Toast?.[method]) {
		window.OCP.Toast[method](message)
	}
}

function showDevicePicker(devices) {
	return new Promise((resolve) => {
		const overlay = document.createElement('div')
		overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:10000;display:flex;align-items:center;justify-content:center'
		const box = document.createElement('div')
		box.style.cssText = 'background:var(--color-main-background,#fff);color:var(--color-main-text,#222);padding:20px;border-radius:8px;min-width:280px;max-width:90vw'
		const title = document.createElement('h3')
		title.textContent = t('shake_localsend', '送り先の端末を選ぶ')
		title.style.marginTop = '0'
		box.appendChild(title)
		const close = (value) => {
			overlay.remove()
			resolve(value)
		}
		for (const device of devices) {
			const button = document.createElement('button')
			button.className = 'button'
			button.style.cssText = 'display:block;width:100%;margin:6px 0;text-align:left'
			button.textContent = `${device.alias}（${device.deviceType}）`
			button.addEventListener('click', () => close(device))
			box.appendChild(button)
		}
		const cancel = document.createElement('button')
		cancel.className = 'button'
		cancel.style.cssText = 'display:block;width:100%;margin-top:12px'
		cancel.textContent = t('shake_localsend', 'キャンセル')
		cancel.addEventListener('click', () => close(null))
		box.appendChild(cancel)
		overlay.addEventListener('click', (event) => {
			if (event.target === overlay) {
				close(null)
			}
		})
		overlay.appendChild(box)
		document.body.appendChild(overlay)
	})
}

registerFileAction(new FileAction({
	id: 'shake-localsend',
	displayName: () => t('shake_localsend', 'LocalSendで送る'),
	iconSvgInline: () => '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/></svg>',
	enabled: (nodes) => nodes.length === 1 && nodes[0].type === FileType.File,
	exec: async (node) => {
		let devices
		try {
			const response = await axios.get(generateUrl('/apps/shake_localsend/devices'))
			devices = response.data.devices
		} catch (error) {
			toast('error', error?.response?.data?.error
				|| t('shake_localsend', '端末一覧を取得できません'))
			return false
		}
		if (!devices || devices.length === 0) {
			toast('error', t('shake_localsend',
				'端末が見つかりません。送り先でLocalSendを開いてください'))
			return false
		}
		const device = await showDevicePicker(devices)
		if (!device) {
			return false
		}
		try {
			await axios.post(generateUrl('/apps/shake_localsend/send'), {
				fileId: node.fileid,
				fingerprint: device.fingerprint,
			})
			toast('success', t('shake_localsend', '送信しました（{device}）',
				{ device: device.alias }))
			return true
		} catch (error) {
			toast('error', error?.response?.data?.error
				|| t('shake_localsend', '送信に失敗しました'))
			return false
		}
	},
	order: 26,
}))
