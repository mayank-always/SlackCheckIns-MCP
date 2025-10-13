const dayjs = require('dayjs');
const CheckInAgent = require('../agent/checkinAgent');

function badRequest(message) {
  const error = new Error(message);
  error.status = 400;
  return error;
}

function ensureArray(value, fieldName) {
  if (!Array.isArray(value)) {
    throw badRequest(`${fieldName} must be an array.`);
  }
  return value;
}

function ensureCheckins(checkins) {
  const items = ensureArray(checkins, 'checkins');
  return items.map((item) => {
    if (!item.message_id || !item.user_id || !item.timestamp) {
      throw badRequest('Each check-in entry must include message_id, user_id, and timestamp.');
    }
    return item;
  });
}

async function handleAgentQuery(req, res, next) {
  try {
    const { question, checkins, roster } = req.body;

    if (!question) {
      throw badRequest('A natural language question is required.');
    }

    const normalizedCheckins = ensureCheckins(checkins || []);
    const agent = new CheckInAgent({ checkins: normalizedCheckins, roster });
    const response = agent.answerQuestion(question);

    res.json({
      question,
      response,
    });
  } catch (error) {
    if (!error.status) {
      error.status = 500;
    }
    next(error);
  }
}

async function generateAgentReport(req, res, next) {
  try {
    const { user, timeframe, checkins, roster } = req.body;

    if (!user || (!user.id && !user.user_id)) {
      throw badRequest('A user object with an id is required.');
    }

    if (!timeframe) {
      throw badRequest('A timeframe payload is required.');
    }

    const normalizedCheckins = ensureCheckins(checkins || []);
    const agent = new CheckInAgent({ checkins: normalizedCheckins, roster });
    const dashboard = agent.generateDashboard({
      userId: user.id || user.user_id,
      userName: user.name || user.display_name || user.real_name,
      timeframe,
    });

    res.json({
      generated_at: dayjs().toISOString(),
      dashboard,
    });
  } catch (error) {
    if (!error.status) {
      error.status = 500;
    }
    next(error);
  }
}

module.exports = {
  handleAgentQuery,
  generateAgentReport,
};
