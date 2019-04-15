const db = require("../../lib/db");

module.exports = async (req, res) => {
  const profiles = await db.query(`
      SELECT *
      FROM data
    `);
  res.end(JSON.stringify({ profiles }));
};
