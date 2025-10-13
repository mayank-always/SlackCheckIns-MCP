const { WebClient } = require('@slack/web-api');

class SlackService {
  constructor(token) {
    if (!token) {
      console.warn('Slack bot token is not set. API calls will fail until SLACK_BOT_TOKEN is configured.');
    }

    this.client = token ? new WebClient(token) : null;
  }

  async fetchChannelMessages({ channelId, oldest, latest }) {
    if (!this.client) {
      throw new Error('Slack Web API client is not configured. Please set the SLACK_BOT_TOKEN environment variable.');
    }

    const aggregated = [];
    let hasMore = true;
    let cursor;

    while (hasMore) {
      const response = await this.client.conversations.history({
        channel: channelId,
        oldest,
        latest,
        limit: 200,
        cursor,
        inclusive: true,
      });

      if (!response.ok) {
        throw new Error(`Slack API error: ${response.error}`);
      }

      const messages = response.messages || [];
      aggregated.push(...messages);
      hasMore = response.has_more;
      cursor = response.response_metadata?.next_cursor;
    }

    return aggregated.filter((message) => !message.subtype && !!message.text);
  }

  async fetchUserProfile(userId) {
    if (!this.client) {
      throw new Error('Slack Web API client is not configured. Please set the SLACK_BOT_TOKEN environment variable.');
    }

    const response = await this.client.users.info({ user: userId });

    if (!response.ok) {
      throw new Error(`Unable to fetch profile for user ${userId}: ${response.error}`);
    }

    return response.user;
  }
}

module.exports = new SlackService(process.env.SLACK_BOT_TOKEN);
