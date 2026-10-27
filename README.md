# 晴空电视 · 直播源自动更新

每 6 小时采集公开 IPv4 频道列表并使用 FFmpeg 解码短样本；成功结果发布到 `public/live/channels.m3u`，检查记录为 `public/live/audit.json`。

订阅地址：https://raw.githubusercontent.com/banbanhang/bravia-live-sources/main/public/live/channels.m3u

完整候选目录：https://raw.githubusercontent.com/banbanhang/bravia-live-sources/main/public/live/candidates.m3u

完整目录保留原始分组及 tvg-id / tvg-language / tvg-country；候选尚未验证，不表示可以播放。应用在本机完成检查后才显示可播线路。

候选目录只合并完全相同的频道/分组/地址/请求头/元数据记录；同一地址在不同频道或分组下的条目不再被覆盖。应用目录保留尚未检查或检查失败的条目并标注状态，用户可确认后手动尝试；目录存在不等于播放成功。

## 工作方式

- 从 vbskycn/iptv、ngo5/IPTV 的公开目录获取候选；不扫描公网 IP、不使用个人播放列表或付费账号。
- 工作流先发布完整候选目录，然后六路并行检查全部候选，不再只截取前 120 条；每条解码六秒。至少取得三个采样帧、解码高度至少 720p 且进程正常退出才进入已解码目录，历史“春晚频道”单独接受 480p，应用由用户选择旧片兼容模式后播放。保留“春晚频道、音乐频道、直播中国”等分组，过滤更新时间和支持作者占位视频。
- 不因清单日期较早而排除能解码的线路；解码通过不证明实时性、台标身份、原生画质或长期稳定性。
- 整轮没有成功线路时保留上一次 M3U，检查报告作为 Actions 附件保留。
- 工作流北京时间约 02:23、08:23、14:23、20:23 触发，GitHub 实际执行可能延迟。也可在 Actions 手动运行。

## 来源与许可

采集器和工作流为晴空电视项目自行实现，按 GPL-3.0 分发，见 LICENSE。目录来自 https://github.com/vbskycn/iptv （GPL-3.0）和 https://github.com/ngo5/IPTV （未核得统一标准仓库许可），仅运行时取得公开地址，不复制其程序源码、台标或频道视频。视频及节目权利属于相应权利人；地址目录不构成节目授权。FFmpeg 由运行环境单独安装，遵守对应构建许可。

此仓库仅发布采集脚本与运行结果，不包含 Android 项目的个人订阅、凭据或构建产物。
