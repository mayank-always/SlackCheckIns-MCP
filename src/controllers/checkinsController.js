const dayjs = require('dayjs');
const slackService = require('../services/slackService');
const { normalizeCheckins } = require('../utils/checkinTransformer');

const ISO_DATE = 'YYYY-MM-DD';

function badRequest(message) {
  const error = new Error(message);
  error.status = 400;
  return error;
}

function validateDateRange(startDate, endDate) {
  if (!startDate || !endDate) {
    throw badRequest('start_date and end_date query parameters are required.');
  }

  const start = dayjs(startDate, ISO_DATE, true);
  const end = dayjs(endDate, ISO_DATE, true);

  if (!start.isValid() || !end.isValid()) {
    throw badRequest('Dates must use the YYYY-MM-DD format.');
  }

  if (end.isBefore(start)) {
    throw badRequest('end_date must be on or after start_date.');
  }

  return { start, end };
}

async function getCheckins(req, res, next) {
  try {
    const { channel_id: channelId, start_date: startDate, end_date: endDate } = req.query;

    if (!channelId) {
      throw badRequest('channel_id query parameter is required.');
    }

    const { start, end } = validateDateRange(startDate, endDate);

    const messages = await slackService.fetchChannelMessages({
      channelId,
      oldest: start.startOf('day').unix(),
      latest: end.endOf('day').unix(),
    });

    const normalized = await normalizeCheckins(messages, slackService);

    res.json({
      channel_id: channelId,
      start_date: start.format(ISO_DATE),
      end_date: end.format(ISO_DATE),
      count: normalized.length,
      results: normalized,
    });
  } catch (error) {
    if (!error.status) {
      error.status = error.message && error.message.includes('Slack') ? 502 : 500;
    }
    next(error);
  }
}

module.exports = {
  getCheckins,
};
