const db = require("../../lib/db");
const url = require("url");

module.exports = async (req, res) => {
  const { query } = url.parse(req.url, true);
  const [profile] = await db.query(`
    SELECT *
    FROM data
    WHERE id = ${query.id}
  `);
  res.end(JSON.stringify({ profile }));
};
