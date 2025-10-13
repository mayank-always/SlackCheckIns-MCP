const express = require('express');
const { getCheckins } = require('../controllers/checkinsController');

const router = express.Router();

router.get('/', getCheckins);

module.exports = router;
