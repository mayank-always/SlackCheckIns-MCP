require('dotenv').config();
const express = require('express');
const checkinsRouter = require('./src/routes/checkins');
const agentRouter = require('./src/routes/agent');

const app = express();
app.use(express.json());

app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

app.use('/api/checkins', checkinsRouter);
app.use('/api/agent', agentRouter);

app.use((err, _req, res, _next) => {
  console.error(err);
  const status = err.status || 500;
  res.status(status).json({
    error: err.message || 'Unexpected error',
  });
});

const port = process.env.PORT || 3000;

if (process.env.NODE_ENV !== 'test') {
  app.listen(port, () => {
    console.log(`Slack Check-in Analysis MCP listening on port ${port}`);
  });
}

module.exports = app;
