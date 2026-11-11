# Elasticsearch 自定义镜像：官方镜像 + IK 中文分词插件
#
# 为什么不用官方镜像直接跑：
# 中文检索需要中文分词器，官方镜像不自带 IK；用 build 才能在镜像里装好插件。
# 本项目语料是英文说明书、查询是中文，中文分词主要作用在查询侧与术语索引，
# 因此即使插件装不上，也可以改成用官方镜像直接跑（把 BASE_IMAGE 指向官方同名镜像、
# 再注释掉下面那行 elasticsearch-plugin install）。
#
# 三个可调参数（改这里就够，不用动 docker-compose.yaml）：
#   ES_VERSION  基础镜像版本，必须与 IK_VERSION 完全一致（ES 插件强校验版本）
#   BASE_IMAGE  基础镜像来源。默认 docker.elastic.co；国内拉不动时换成 Docker Hub 的
#               elasticsearch:8.19.10（官方同名镜像，内容一致；注意改完要删旧镜像重建）
#   IK_VERSION  IK 插件版本
#
# 2026-11 修正：IK 插件已不在 GitHub Releases 发布（旧的
#   https://github.com/infinilabs/analysis-ik/releases/download/v8.19.10/... 返回 404），
# 现在统一从 release.infinilabs.com 取；也可用官方的 get.infini.cloud 短链。
ARG ES_VERSION=8.19.10
ARG BASE_IMAGE=docker.elastic.co/elasticsearch/elasticsearch:${ES_VERSION}
FROM ${BASE_IMAGE}

ARG IK_VERSION=8.19.10
RUN bin/elasticsearch-plugin install --batch \
    https://release.infinilabs.com/analysis-ik/stable/elasticsearch-analysis-ik-${IK_VERSION}.zip
