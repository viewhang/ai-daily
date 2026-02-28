## AIDaily

每天获取最新的ai咨询


- resources/rss.ompl 400个左右订阅源
- daily-news-to-html.py  读取过去24h内信息存储到html
- daily-news-send.py  每隔半小时读取过去半小时内信息流发送到discord，并存储到html


TODO：

- [ ] 优化评分系统
- [ ] 及时推送如何避免重复
- [ ] 每天早报如何避免重复
- [ ] 早报内容格式优化：参考appso /xiaohu / ai gap
- [ ] 增加图片/信息图
- [ ] 推送到知乎 / 小红书 / 网站

## 订阅源说明

RSS 订阅源 文件来源于 [BestBlogs](https://www.bestblogs.dev/en/sources)，目前已更新到420个左右。

[订阅源说明参考](BestBlogs_RSS_ALL.opml: https://github.com/ginobefun/BestBlogs/blob/main/BestBlogs_RSS_ALL.opml)

据称有以下几个大类：

- 文章类（170 个订阅源）：
  - 其中微信公众号 120个： 以`https://wechat2rss.bestblogs.dev/` 开头
- 播客类（30 个订阅源）：
- 视频类（40 个订阅源）：以`https://www.youtube.com/feeds` 开头
- Twitter 类（160 个订阅源）： 以`https://api.xgo.ing/` 开头进行转接

涵盖了主流中外媒体，x热门博主，微信热门公众号，主流AI科技公司博客等

## 其它参考

- https://news.smol.ai/
