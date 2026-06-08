ARG BASE_IMAGE=ghcr.io/kuhl-haus/kuhl-haus-mdp-app-server:latest

FROM ${BASE_IMAGE}

ARG user=py4web

USER root
COPY password.txt /home/$user/
RUN chown "${user}:${user}" /home/$user/password.txt

EXPOSE 8000

USER $user
WORKDIR /home/$user/
ENTRYPOINT ["/home/py4web/app-entrypoint.sh"]