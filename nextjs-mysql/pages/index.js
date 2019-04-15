import fetch from "isomorphic-unfetch";
import Head from "next/head";
import Link from "next/link";

function HomePage({ profiles }) {
  return (
    <>
      <Head>
        <title>Profiles</title>
        <link rel="shortcut icon" href="/static/favicon.ico" />
        <link
          rel="stylesheet"
          href="https://css.zeit.sh/v1.css"
          type="text/css"
        />
      </Head>
      <h1>Robot Profiles</h1>
      <ul>
        {profiles.map(p => (
          <li key={p.id}>
            <img src={p.avatar} />
            <Link prefetch href={`/profile?id=${p.id}`}>
              <h2>{p.name}</h2>
            </Link>
          </li>
        ))}
      </ul>
      <style jsx>{`
        ul li::before {
          content: "";
        }
        li {
          display: flex;
        }
        h2 {
          cursor: pointer;
        }
      `}</style>
    </>
  );
}

HomePage.getInitialProps = async ({ req }) => {
  const host = req ? `https://${req.headers.host}` : "";
  const res = await fetch(`${host}/api/profiles`);
  const json = await res.json();
  return json;
};

export default HomePage;
