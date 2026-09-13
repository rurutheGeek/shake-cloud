import { registerFileAction } from '@nextcloud/files'
import { translate as t } from '@nextcloud/l10n'
import { generateUrl } from '@nextcloud/router'
import axios from '@nextcloud/axios'

const PRINTABLE = ['pdf', 'png', 'jpg', 'jpeg', 'txt']
const toast = (method, message) => {
	if (window.OCP?.Toast?.[method]) {
		window.OCP.Toast[method](message)
	}
}

registerFileAction({
	id: 'shake-print',
	displayName: () => t('shake_print', '印刷'),
	iconSvgInline: () => '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M6 3h12v4H6V3zm-4 6h20v8h-4v4H6v-4H2V9zm4 6v4h12v-4H6zm12-4a1 1 0 1 0 0 2 1 1 0 0 0 0-2z"/></svg>',
	enabled: ({ nodes }) => nodes.length === 1
		&& PRINTABLE.includes((nodes[0].extension || '').toLowerCase().replace(/^\./, '')),
	exec: async ({ nodes }) => {
		const [node] = nodes
		try {
			const { data } = await axios.post(generateUrl('/apps/shake_print/print'), {
				fileId: node.fileid,
			})
			toast('success', t('shake_print', '印刷しました（{job}）', { job: data.job }))
			return true
		} catch (error) {
			toast('error', error?.response?.data?.error || t('shake_print', '印刷に失敗しました'))
			return false
		}
	},
	order: 25,
})
