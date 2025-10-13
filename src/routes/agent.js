const express = require('express');
const { handleAgentQuery, generateAgentReport } = require('../controllers/agentController');

const router = express.Router();

router.post('/query', handleAgentQuery);
router.post('/report', generateAgentReport);

module.exports = router;
