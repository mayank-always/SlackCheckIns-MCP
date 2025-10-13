const dayjs = require('dayjs');
const customParseFormat = require('dayjs/plugin/customParseFormat');
const isoWeek = require('dayjs/plugin/isoWeek');
const weekday = require('dayjs/plugin/weekday');
const isSameOrAfter = require('dayjs/plugin/isSameOrAfter');
const isSameOrBefore = require('dayjs/plugin/isSameOrBefore');
const { classifyCheckinQuality } = require('../utils/checkinQuality');

dayjs.extend(customParseFormat);
dayjs.extend(isoWeek);
dayjs.extend(weekday);
dayjs.extend(isSameOrAfter);
dayjs.extend(isSameOrBefore);

const ISO_DATE = 'YYYY-MM-DD';
const QUALITY_TO_SCORE = {
  Strong: 3,
  Medium: 2,
  Weak: 1,
};

function normalizeRoster(roster = []) {
  return roster.map((entry) => {
    if (typeof entry === 'string') {
      return { id: entry, name: entry };
    }

    if (entry && typeof entry === 'object') {
      return {
        id: entry.id || entry.user_id || entry.email || entry.name,
        name: entry.name || entry.display_name || entry.real_name || entry.id,
      };
    }

    return null;
  }).filter(Boolean);
}

function uniqueUsersFromCheckins(checkins) {
  const map = new Map();
  checkins.forEach((item) => {
    if (!map.has(item.user_id)) {
      map.set(item.user_id, { id: item.user_id, name: item.user_name || item.user_id });
    }
  });
  return Array.from(map.values());
}

function normalizeQuality(quality, content) {
  if (quality) {
    return quality;
  }
  return classifyCheckinQuality(content || '');
}

class CheckInAgent {
  constructor({ checkins = [], roster = [] } = {}) {
    this.checkins = checkins.map((checkin) => ({
      ...checkin,
      timestamp: checkin.timestamp,
      quality: normalizeQuality(checkin.quality, checkin.message_content),
    }));
    this.roster = normalizeRoster(roster);
  }

  getAllStudents() {
    const uniqueUsers = uniqueUsersFromCheckins(this.checkins);
    const combined = new Map();

    [...this.roster, ...uniqueUsers].forEach((entry) => {
      if (!combined.has(entry.id)) {
        combined.set(entry.id, entry);
      }
    });

    return Array.from(combined.values());
  }

  getCheckinsByDateRange(start, end) {
    const startDate = dayjs(start);
    const endDate = dayjs(end);

    return this.checkins.filter((checkin) => {
      const timestamp = dayjs(checkin.timestamp);
      return timestamp.isSameOrAfter(startDate) && timestamp.isSameOrBefore(endDate);
    });
  }

  getCheckinsForUser(userId, start, end) {
    const dateFiltered = start && end ? this.getCheckinsByDateRange(start, end) : this.checkins;
    return dateFiltered.filter((checkin) => checkin.user_id === userId);
  }

  getUserByName(name) {
    const normalizedName = (name || '').trim().toLowerCase();
    return this.getAllStudents().find((user) => user.name.toLowerCase() === normalizedName);
  }

  summarizeDaily(userId, date) {
    const dayStart = dayjs(date).startOf('day');
    const dayEnd = dayjs(date).endOf('day');
    const entries = this.getCheckinsForUser(userId, dayStart, dayEnd);

    if (!entries.length) {
      return null;
    }

    const [entry] = entries.sort((a, b) => dayjs(a.timestamp).valueOf() - dayjs(b.timestamp).valueOf());

    return {
      date: dayStart.format(ISO_DATE),
      message: entry.message_content,
      quality: entry.quality,
      timestamp: entry.timestamp,
    };
  }

  summarizeRange(userId, start, end) {
    const entries = this.getCheckinsForUser(userId, start, end);

    if (!entries.length) {
      return null;
    }

    const score = entries.reduce((acc, item) => acc + (QUALITY_TO_SCORE[item.quality] || 0), 0);
    const averageScore = score / entries.length;
    const quality = averageScore >= 2.5 ? 'Strong' : averageScore >= 1.75 ? 'Medium' : 'Weak';

    return {
      start: dayjs(start).format(ISO_DATE),
      end: dayjs(end).format(ISO_DATE),
      total_checkins: entries.length,
      average_quality_score: Number(averageScore.toFixed(2)),
      quality,
      entries,
    };
  }

  summarizeWeek(userId, weekStart) {
    const start = dayjs(weekStart).startOf('day');
    const end = start.add(6, 'day').endOf('day');
    const summary = this.summarizeRange(userId, start, end);

    if (!summary) {
      return null;
    }

    const blockers = this.extractBlockers(summary.entries);

    return {
      ...summary,
      blockers,
    };
  }

  summarizeMonth(userId, month) {
    const start = dayjs(month).startOf('month');
    const end = dayjs(month).endOf('month');
    const summary = this.summarizeRange(userId, start, end);

    if (!summary) {
      return null;
    }

    const consistency = this.calculateConsistency(userId, start, end);
    const blockers = this.extractBlockers(summary.entries);

    return {
      ...summary,
      consistency,
      blockers,
    };
  }

  calculateConsistency(userId, start, end) {
    const entries = this.getCheckinsForUser(userId, start, end);
    if (!entries.length) {
      return { days_checked_in: 0, period_length: dayjs(end).diff(start, 'day') + 1, percentage: 0 };
    }

    const uniqueDays = new Set(entries.map((entry) => dayjs(entry.timestamp).format(ISO_DATE)));
    const totalDays = dayjs(end).diff(start, 'day') + 1;

    return {
      days_checked_in: uniqueDays.size,
      period_length: totalDays,
      percentage: Number(((uniqueDays.size / totalDays) * 100).toFixed(2)),
    };
  }

  extractBlockers(entries) {
    const blockerKeywords = ['blocker', 'blocked', 'stuck', 'issue', 'problem', 'waiting', 'delay'];
    const blockers = [];

    entries.forEach((entry) => {
      const lower = entry.message_content.toLowerCase();
      const hasBlocker = blockerKeywords.some((keyword) => lower.includes(keyword));
      if (hasBlocker) {
        blockers.push({
          user_id: entry.user_id,
          user_name: entry.user_name,
          timestamp: entry.timestamp,
          message: entry.message_content,
        });
      }
    });

    return blockers;
  }

  findMissingCheckins(start, end) {
    const students = this.getAllStudents();
    const checkins = this.getCheckinsByDateRange(start, end);
    const hasCheckedIn = new Set(checkins.map((entry) => entry.user_id));

    return students.filter((student) => !hasCheckedIn.has(student.id));
  }

  answerQuestion(question) {
    const lower = question.toLowerCase();

    if (lower.includes('who checked in yesterday')) {
      return this.answerYesterday();
    }

    if (lower.includes("who didn't") || lower.includes('who did not')) {
      return this.answerMissingRecent(lower);
    }

    if (lower.includes('quality of')) {
      return this.answerQualityQuestion(question);
    }

    if (lower.includes('substantial progress')) {
      return this.answerProgressThisWeek();
    }

    if (lower.includes('between') && lower.includes('checked in')) {
      return this.answerDateRangeListing(question);
    }

    if (lower.includes('key blockers') || lower.includes('blockers')) {
      return this.answerBlockersThisWeek();
    }

    return {
      question,
      answer: "I'm not sure how to answer that yet, but I can help with check-in summaries, quality, blockers, and attendance.",
    };
  }

  answerYesterday() {
    const today = dayjs();
    const day = today.subtract(1, 'day').format(ISO_DATE);
    const start = dayjs(day).startOf('day');
    const end = dayjs(day).endOf('day');
    const entries = this.getCheckinsByDateRange(start, end);
    const checkinsByUser = new Map();
    entries.forEach((entry) => {
      checkinsByUser.set(entry.user_id, entry.user_name);
    });

    const missing = this.findMissingCheckins(start, end);
    const rosterProvided = this.roster.length > 0;

    return {
      question: 'Who checked in yesterday and who did not?',
      date: day,
      checked_in: Array.from(checkinsByUser.values()),
      missing: rosterProvided ? missing.map((student) => student.name) : [],
      note: rosterProvided ? undefined : 'Provide a roster list to identify missing check-ins.',
    };
  }

  answerMissingRecent(lowerQuestion) {
    const match = lowerQuestion.match(/past (\d+) day/);
    const days = match ? Number(match[1]) : 3;
    const end = dayjs().endOf('day');
    const start = end.subtract(days - 1, 'day').startOf('day');
    const missing = this.findMissingCheckins(start, end);
    const rosterProvided = this.roster.length > 0;

    return {
      question: 'Students missing check-ins',
      start: start.format(ISO_DATE),
      end: end.format(ISO_DATE),
      missing: rosterProvided ? missing.map((student) => student.name) : [],
      note: rosterProvided ? undefined : 'Provide a roster list to identify missing check-ins.',
    };
  }

  answerQualityQuestion(question) {
    const nameMatch = question.match(/quality of ([^?]+?)'s check-in/i);
    const dateMatch = question.match(/on ([^?]+?)(\?|$)/i);

    if (!nameMatch) {
      return { question, answer: 'Please specify the student name whose check-in quality you want to review.' };
    }

    const studentName = nameMatch[1].trim();
    const user = this.getUserByName(studentName);

    if (!user) {
      return { question, answer: `I could not find a student named ${studentName}.` };
    }

    const date = dateMatch ? this.parseDateToken(dateMatch[1]) : dayjs().format(ISO_DATE);
    if (!date) {
      return { question, answer: 'I was unable to interpret the requested date.' };
    }

    const daily = this.summarizeDaily(user.id, date);
    if (!daily) {
      return { question, answer: `${studentName} did not check in on ${dayjs(date).format(ISO_DATE)}.` };
    }

    return {
      question,
      answer: `${studentName}'s check-in on ${daily.date} was classified as ${daily.quality}.`,
      details: daily,
    };
  }

  answerProgressThisWeek() {
    const start = dayjs().startOf('isoWeek');
    const end = start.add(6, 'day').endOf('day');
    const students = this.getAllStudents();
    const rankings = students.map((student) => {
      const summary = this.summarizeRange(student.id, start, end);
      return {
        student: student.name,
        average_quality_score: summary?.average_quality_score || 0,
        quality: summary?.quality || 'No Data',
        checkins: summary?.total_checkins || 0,
      };
    }).filter((item) => item.checkins > 0);

    rankings.sort((a, b) => b.average_quality_score - a.average_quality_score);

    return {
      question: 'Which students made the most substantial progress this week?',
      week_start: start.format(ISO_DATE),
      week_end: end.format(ISO_DATE),
      top_students: rankings.slice(0, 5),
    };
  }

  answerDateRangeListing(question) {
    const match = question.match(/between ([^ ]+) and ([^?]+)/i);
    if (!match) {
      return { question, answer: 'Please specify the start and end dates for the query (e.g., between Monday and Wednesday).' };
    }

    const startToken = match[1];
    const endToken = match[2];
    const start = this.parseDateToken(startToken);
    const end = this.parseDateToken(endToken, start);

    if (!start || !end) {
      return { question, answer: 'I was unable to interpret the provided date range.' };
    }

    const entries = this.getCheckinsByDateRange(dayjs(start).startOf('day'), dayjs(end).endOf('day'));
    const grouped = {};
    entries.forEach((entry) => {
      if (!grouped[entry.user_name]) {
        grouped[entry.user_name] = [];
      }
      grouped[entry.user_name].push({
        date: dayjs(entry.timestamp).format(ISO_DATE),
        message: entry.message_content,
        quality: entry.quality,
      });
    });

    return {
      question,
      start: dayjs(start).format(ISO_DATE),
      end: dayjs(end).format(ISO_DATE),
      students: grouped,
    };
  }

  answerBlockersThisWeek() {
    const start = dayjs().startOf('isoWeek');
    const end = start.add(6, 'day').endOf('day');
    const entries = this.getCheckinsByDateRange(start, end);
    const blockers = this.extractBlockers(entries);

    return {
      question: 'What were the key blockers mentioned this week?',
      week_start: start.format(ISO_DATE),
      week_end: end.format(ISO_DATE),
      blockers,
    };
  }

  parseDateToken(token, referenceStart) {
    const trimmed = token.trim().replace(/\.$/, '');
    const lower = trimmed.toLowerCase();

    if (dayjs(trimmed, ISO_DATE, true).isValid()) {
      return dayjs(trimmed, ISO_DATE, true);
    }

    const weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
    const weekdayIndex = weekdays.indexOf(lower);

    if (weekdayIndex !== -1) {
      const base = referenceStart ? dayjs(referenceStart) : dayjs().startOf('isoWeek');
      return base.add(weekdayIndex, 'day');
    }

    if (lower === 'yesterday') {
      return dayjs().subtract(1, 'day');
    }

    if (lower === 'today') {
      return dayjs();
    }

    if (lower === 'tomorrow') {
      return dayjs().add(1, 'day');
    }

    return null;
  }

  generateDashboard({ userId, userName, timeframe }) {
    if (!userId) {
      throw new Error('userId is required to generate a dashboard.');
    }

    if (!timeframe || !timeframe.type) {
      throw new Error('A timeframe with a type is required (daily, weekly, monthly).');
    }

    const type = timeframe.type.toLowerCase();

    if (type === 'daily') {
      const date = timeframe.date || timeframe.start;
      if (!date) {
        throw new Error('Daily dashboards require a date value.');
      }
      const summary = this.summarizeDaily(userId, date);
      return {
        user: userName,
        type: 'daily',
        date: dayjs(date).format(ISO_DATE),
        summary,
      };
    }

    if (type === 'weekly') {
      const startValue = timeframe.start || timeframe.date;
      const start = startValue ? dayjs(startValue).startOf('isoWeek') : dayjs().startOf('isoWeek');
      const summary = this.summarizeWeek(userId, start);
      return {
        user: userName,
        type: 'weekly',
        week_start: dayjs(start).format(ISO_DATE),
        week_end: dayjs(start).add(6, 'day').format(ISO_DATE),
        summary,
      };
    }

    if (type === 'monthly') {
      const monthValue = timeframe.month || timeframe.start || timeframe.date || dayjs().format(ISO_DATE);
      const summary = this.summarizeMonth(userId, monthValue);
      return {
        user: userName,
        type: 'monthly',
        month: dayjs(monthValue).format('MMMM YYYY'),
        summary,
      };
    }

    throw new Error(`Unsupported timeframe type: ${timeframe.type}`);
  }
}

module.exports = CheckInAgent;
