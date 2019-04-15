import fetch from "isomorphic-unfetch";
import Head from "next/head";
import Link from "next/link";

function ProfilePage({ profile }) {
  return (
    <>
      <Head>
        <title>{profile.name}'s Profile</title>
        <link rel="shortcut icon" href="/static/favicon.ico" />
        <link
          rel="stylesheet"
          href="https://css.zeit.sh/v1.css"
          type="text/css"
        />
      </Head>
      <div>
        <img src={profile.avatar} />
        <h1>{profile.name}</h1>
        <p>{profile.address}</p>
        <p>{profile.email}</p>
        <Link prefetch href="/">
          <a>← Back to profiles</a>
        </Link>
      </div>
      <style jsx>
        {`
          div {
            margin-top: 100px;
          }
        `}
      </style>
    </>
  );
}

ProfilePage.getInitialProps = async ({ req, query }) => {
  const host = req ? `https://${req.headers.host}` : "";
  const res = await fetch(`${host}/api/profiles/${query.id}`);
  const json = await res.json();
  return json;
};

export default ProfilePage;
