import { FileType, registerFileAction } from '@nextcloud/files'
import { translate as t } from '@nextcloud/l10n'
import { generateUrl } from '@nextcloud/router'
import axios from '@nextcloud/axios'

const FIELDS = [
	['title', '曲名'],
	['artist', 'アーティスト'],
	['album', 'アルバム'],
	['albumartist', 'アルバムアーティスト'],
	['tracknumber', 'トラック番号'],
	['discnumber', 'ディスク番号'],
	['date', '年'],
	['genre', 'ジャンル'],
]

const toast = (method, message) => {
	if (window.OCP?.Toast?.[method]) {
		window.OCP.Toast[method](message)
	}
}

function element(tag, text, style) {
	const node = document.createElement(tag)
	if (text) {
		node.textContent = text
	}
	if (style) {
		node.style.cssText = style
	}
	return node
}

async function openEditor(fileId) {
	let tags
	try {
		const response = await axios.get(generateUrl('/apps/shake_tags/tags'), {
			params: { fileId },
		})
		tags = response.data.tags || {}
	} catch (error) {
		toast('error', error?.response?.data?.error
			|| t('shake_tags', 'タグを読み込めません'))
		return false
	}

	return new Promise((resolve) => {
		const overlay = element('div', '', 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:10000;display:flex;align-items:center;justify-content:center')
		const box = element('div', '', 'background:var(--color-main-background,#fff);color:var(--color-main-text,#222);padding:20px;border-radius:8px;width:min(520px,92vw);max-height:90vh;overflow:auto')
		box.appendChild(element('h3', t('shake_tags', 'タグを編集'), 'margin-top:0'))
		const inputs = {}
		for (const [key, label] of FIELDS) {
			const row = element('label', '', 'display:block;margin:6px 0')
			row.appendChild(element('span', label, 'display:block;font-size:12px;opacity:.8'))
			const input = document.createElement('input')
			input.type = 'text'
			input.className = 'input'
			input.style.cssText = 'width:100%'
			input.value = (tags[key] && tags[key][0]) || ''
			inputs[key] = input
			row.appendChild(input)
			box.appendChild(row)
		}
		const candidateBox = element('div', '', 'margin:8px 0')
		box.appendChild(candidateBox)
		const actions = element('div', '', 'display:flex;gap:8px;margin-top:12px;flex-wrap:wrap')
		box.appendChild(actions)
		const close = (value) => {
			overlay.remove()
			resolve(value)
		}
		const search = element('button', t('shake_tags', 'MusicBrainzで検索'), '')
		search.className = 'button'
		search.addEventListener('click', async () => {
			candidateBox.textContent = ''
			candidateBox.appendChild(element('p', t('shake_tags', '検索中...'),
				'font-size:13px;opacity:.8'))
			try {
				const response = await axios.get(generateUrl('/apps/shake_tags/search'), {
					params: {
						artist: inputs.artist.value,
						title: inputs.title.value,
						album: inputs.album.value,
					},
				})
				const candidates = response.data.candidates || []
				candidateBox.textContent = ''
				if (candidates.length === 0) {
					candidateBox.appendChild(element('p',
						t('shake_tags', '候補が見つかりません'),
						'font-size:13px;opacity:.8'))
					return
				}
				candidateBox.appendChild(element('span', t('shake_tags', '候補'),
					'display:block;font-size:12px;opacity:.8'))
				for (const candidate of candidates) {
					const button = element('button',
						`${candidate.title} / ${candidate.artist} / ${candidate.album} (${candidate.date})`,
						'display:block;width:100%;text-align:left;margin:4px 0')
					button.className = 'button'
					button.addEventListener('click', () => {
						inputs.title.value = candidate.title || inputs.title.value
						inputs.artist.value = candidate.artist || inputs.artist.value
						inputs.album.value = candidate.album || inputs.album.value
						inputs.albumartist.value = inputs.albumartist.value || candidate.artist || ''
						if (candidate.date) {
							inputs.date.value = candidate.date
						}
						candidateBox.textContent = ''
					})
					candidateBox.appendChild(button)
				}
			} catch (error) {
				candidateBox.textContent = ''
				toast('error', error?.response?.data?.error
					|| t('shake_tags', 'MusicBrainzを検索できません'))
			}
		})
		actions.appendChild(search)
		const save = element('button', t('shake_tags', '保存'), '')
		save.className = 'button primary'
		save.addEventListener('click', async () => {
			const payload = {}
			for (const [key] of FIELDS) {
				const value = inputs[key].value.trim()
				if (value !== '') {
					payload[key] = value
				}
			}
			try {
				const response = await axios.post(generateUrl('/apps/shake_tags/tags'), {
					fileId,
					tags: payload,
				})
				toast('success', response.data.changed === false
					? t('shake_tags', '変更はありませんでした')
					: t('shake_tags', 'タグを保存しました'))
				close(true)
			} catch (error) {
				toast('error', error?.response?.data?.error
					|| t('shake_tags', 'タグを保存できません'))
			}
		})
		actions.appendChild(save)
		const cancel = element('button', t('shake_tags', 'キャンセル'), '')
		cancel.className = 'button'
		cancel.addEventListener('click', () => close(false))
		actions.appendChild(cancel)
		overlay.addEventListener('click', (event) => {
			if (event.target === overlay) {
				close(false)
			}
		})
		overlay.appendChild(box)
		document.body.appendChild(overlay)
	})
}

registerFileAction({
	id: 'shake-tags',
	displayName: () => t('shake_tags', 'タグを編集'),
	iconSvgInline: () => '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M21.41 11.58l-9-9A2 2 0 0 0 11 2H4a2 2 0 0 0-2 2v7a2 2 0 0 0 .59 1.42l9 9A2 2 0 0 0 13 22a2 2 0 0 0 1.41-.59l7-7A2 2 0 0 0 21.41 11.58zM6.5 8A1.5 1.5 0 1 1 8 6.5 1.5 1.5 0 0 1 6.5 8z"/></svg>',
	enabled: ({ nodes }) => nodes.length === 1
		&& nodes[0].type === FileType.File
		&& (nodes[0].extension || '').toLowerCase().replace(/^\./, '') === 'mp3',
	exec: ({ nodes }) => openEditor(nodes[0].fileid),
	order: 27,
})
