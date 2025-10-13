const STRONG_THRESHOLD = 80;
const MEDIUM_THRESHOLD = 40;

const KEYWORD_GROUPS = {
  progress: ['progress', 'completed', 'finished', 'shipped', 'done', 'achieved'],
  plans: ['plan', 'next', 'today', 'tomorrow', 'focus'],
  blockers: ['blocker', 'stuck', 'issue', 'problem', 'waiting', 'help'],
};

function countWords(text) {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

function scoreCompleteness(text) {
  let score = 0;
  const lower = text.toLowerCase();

  Object.values(KEYWORD_GROUPS).forEach((keywords) => {
    if (keywords.some((keyword) => lower.includes(keyword))) {
      score += 1;
    }
  });

  return score;
}

function scoreSpecificity(text) {
  const numbers = text.match(/\b\d+\b/g) || [];
  const bulletIndicators = (text.match(/[\n\r]-|\*/g) || []).length;
  return Math.min(numbers.length + bulletIndicators, 3);
}

function calculateQualityScore(text) {
  if (!text) {
    return 0;
  }

  const wordCount = countWords(text);
  const completeness = scoreCompleteness(text) * 15;
  const specificity = scoreSpecificity(text) * 10;
  const lengthScore = Math.min(wordCount, 120) * 0.25;

  return completeness + specificity + lengthScore;
}

function classifyCheckinQuality(text) {
  const score = calculateQualityScore(text);

  if (score >= STRONG_THRESHOLD) {
    return 'Strong';
  }

  if (score >= MEDIUM_THRESHOLD) {
    return 'Medium';
  }

  return 'Weak';
}

module.exports = {
  classifyCheckinQuality,
  calculateQualityScore,
};
