import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("collector", pathlib.Path(__file__).parents[1] / "refresh_live_sources.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class CollectorTests(unittest.TestCase):
    def test_metadata_and_special_groups_survive_publication(self):
        text = '#EXTM3U\n#EXTINF:-1 group-title="春晚频道" tvg-id="spring.cn" tvg-language="zho",2005年春晚\nhttps://example.org/spring.m3u8'
        rows = collector.parse(text, 'https://example.org/list')
        self.assertEqual('春晚频道', rows[0]['group'])
        self.assertEqual('zho', rows[0]['metadata']['tvg-language'])
        self.assertEqual(rows, collector.parse(collector.m3u(rows), 'https://example.org/list'))

    def test_catalog_only_keeps_every_candidate_without_claiming_playability(self):
        rows = [dict(name=str(i), group='直播中国', url=f'https://example.org/{i}', headers={}, source='https://example.org/list') for i in range(130)]
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch('sys.argv', ['collector', '--output', folder, '--catalog-only']), mock.patch.object(collector, 'download', return_value=rows), mock.patch.object(collector, 'probe') as probe:
                self.assertEqual(0, collector.main())
                probe.assert_not_called()
            self.assertEqual(130, (pathlib.Path(folder) / 'candidates.m3u').read_text(encoding='utf-8').count('#EXTINF:'))
            self.assertFalse((pathlib.Path(folder) / 'channels.m3u').exists())

    def test_default_decode_covers_more_than_first_120_routes(self):
        rows = [dict(name=str(i), group='电影频道', url=f'https://example.org/{i}', headers={}, source='https://example.org/list') for i in range(130)]
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch('sys.argv', ['collector', '--output', folder]), mock.patch.object(collector, 'download', return_value=rows), mock.patch.object(collector, 'probe', side_effect=lambda row, _: dict(row, ok=True)) as probe:
                self.assertEqual(0, collector.main())
                self.assertEqual(130, probe.call_count)

    def test_support_author_video_is_not_a_tv_channel(self):
        text = '#EXTM3U\n#EXTINF:-1,支持作者\nhttps://example.org/support.mp4\n#EXTINF:-1,CCTV13\nhttps://example.org/live.m3u8'
        rows = collector.parse(text, 'https://example.org/list')
        self.assertEqual(['CCTV13'], [row['name'] for row in rows])

    def test_m3u_headers_and_placeholder(self):
        rows = collector.parse('#EXTM3U\n#EXTINF:-1 group-title="央视,卫视",CCTV1\n#EXTVLCOPT:http-referrer=https://example.org/\nhttps://example.org/1.m3u8\n#EXTINF:-1 group-title="更新时间",2026-10-27\nhttps://example.org/date.mp4', 'https://example.org/list')
        self.assertEqual(1, len(rows))
        self.assertEqual('央视,卫视', rows[0]['group'])
        self.assertEqual('https://example.org/', rows[0]['headers']['Referer'])
        self.assertEqual(rows, collector.parse(collector.m3u(rows), 'https://example.org/list'))

    def test_txt_multi_routes_and_no_header_leak(self):
        rows = collector.parse('央视,#genre#\nCCTV1,https://example.org/a#https://example.org/b|User-Agent=My+TV\nCCTV2,https://example.org/c', 'https://example.org/list')
        self.assertEqual(3, len(rows))
        self.assertEqual('My TV', rows[1]['headers']['User-Agent'])
        self.assertEqual({}, rows[2]['headers'])

    def test_credentials_and_header_injection_rejected(self):
        self.assertFalse(collector.web_url('https://u:p@example.org/a'))
        self.assertFalse(collector.web_url('file:///a'))
        rows = collector.parse('A,https://example.org/a|User-Agent=a%0d%0aInjected:b', 'https://example.org/list')
        self.assertEqual([], rows)

    def test_failed_decode_does_not_replace_previous_working_list(self):
        row = dict(name='CCTV1', group='央视', url='https://example.org/live', headers={}, source='https://example.org/list')
        with tempfile.TemporaryDirectory() as folder:
            target = pathlib.Path(folder) / 'channels.m3u'
            target.write_text('#EXTM3U\nprevious working list\n', encoding='utf-8')
            with mock.patch('sys.argv', ['collector', '--output', folder]), mock.patch.object(collector, 'download', return_value=[row]), mock.patch.object(collector, 'probe', return_value=dict(row, ok=False)):
                self.assertEqual(1, collector.main())
            self.assertIn('previous working list', target.read_text(encoding='utf-8'))
            self.assertTrue((pathlib.Path(folder) / 'audit.json').exists())

    def test_successful_decode_publishes_new_list(self):
        row = dict(name='CCTV1', group='央视', url='https://example.org/live', headers={}, source='https://example.org/list')
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch('sys.argv', ['collector', '--output', folder]), mock.patch.object(collector, 'download', return_value=[row]), mock.patch.object(collector, 'probe', return_value=dict(row, ok=True, width=1920, height=1080, decodedSamples=6)):
                self.assertEqual(0, collector.main())
            self.assertIn('CCTV1', (pathlib.Path(folder) / 'channels.m3u').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
