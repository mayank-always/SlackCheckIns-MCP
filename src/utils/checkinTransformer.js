const { classifyCheckinQuality } = require('./checkinQuality');

function toIsoString(timestamp) {
  const [seconds, decimals = '0'] = String(timestamp).split('.');
  const millis = Number(`${seconds}.${decimals}`) * 1000;
  return new Date(millis).toISOString();
}

async function resolveUserName(slackService, userId, cache) {
  if (!userId) {
    return 'Unknown User';
  }

  if (cache.has(userId)) {
    return cache.get(userId);
  }

  try {
    const profile = await slackService.fetchUserProfile(userId);
    const displayName = profile?.profile?.display_name || profile?.real_name || userId;
    cache.set(userId, displayName);
    return displayName;
  } catch (error) {
    cache.set(userId, userId);
    return userId;
  }
}

async function normalizeCheckins(messages, slackService) {
  const userCache = new Map();
  const normalized = [];

  for (const message of messages) {
    const cachedProfileName = message.user_profile?.display_name || message.user_profile?.real_name;
    if (cachedProfileName) {
      userCache.set(message.user, cachedProfileName);
    }

    const userName = await resolveUserName(slackService, message.user, userCache);
    normalized.push({
      message_id: message.ts,
      user_id: message.user,
      user_name: userName,
      timestamp: toIsoString(message.ts),
      message_content: message.text,
      quality: classifyCheckinQuality(message.text),
    });
  }

  return normalized;
}

module.exports = {
  normalizeCheckins,
};
