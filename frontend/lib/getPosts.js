import fetch from "isomorphic-fetch"
import mdxPrism from 'mdx-prism'
// import { serialize } from "next-mdx-remote/serialize";
import renderToString from 'next-mdx-remote/render-to-string'
import readingTime from 'reading-time'

import MDXComponents from '../components/MDXComponents'

const PAGE_SIZE = 50


export async function getPosts() {
  const response = await fetch(`${process.env.BACKEND_URI}/posts`);
  const respJson = await response.json();
  const posts = respJson;

  return posts;
}

export async function getAllPosts() {
  const response = await fetch(`${process.env.BACKEND_URI}/posts?page=0&size=1`)
  const respJson = await response.json()
  const totalItems = respJson['total']
  const totalPages = Math.ceil(totalItems / PAGE_SIZE)

  const fetchPages = []
  for (let page = 0; page < totalPages; page++) {
    const url = `${process.env.BACKEND_URI}/posts?page=${page}&size=${PAGE_SIZE}`

    fetchPages.push(fetch(url).then(res => res.json()))
  }

  const pagesData = await Promise.all(fetchPages)
  const allPosts = pagesData.flatMap(p => p['items'])

  return allPosts
}

export async function getPostBySlug(slug) {
  const data = {}
  const response_slug = await fetch(`${process.env.BACKEND_URI}/posts/${slug}`);
  const RespJsonSlug = await response_slug.json();

  data['title'] = RespJsonSlug['title']
  data['summary'] = RespJsonSlug['summary']
  data['published_at'] = RespJsonSlug['published_at']
  const content = RespJsonSlug['body']

  const response_user = await fetch(`${process.env.BACKEND_URI}/users/user?user_id=${RespJsonSlug['author_id']}`);
  const RespJsonUser = await response_user.json()
  data['user'] = RespJsonUser['username']

  // const mdxSource = await serialize(content)
  const mdxSource = await renderToString(content, {
    components: MDXComponents,
    mdxOptions: {
      remarkPlugins: [
        require('remark-autolink-headings'),
        require('remark-slug'),
        require('remark-code-titles'),
      ],
      rehypePlugins: [mdxPrism]
    }
  })

  return {
    mdxSource,
    frontMatter: {
      wordCount: content.split(/\s+/gu).length,
      readingTime: readingTime(content),
      slug: slug || null,
      ...data
    }
  }

}
