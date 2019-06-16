create table if not exists memes
(
  guild_id   bigint                                                         not null,
  name       varchar(128)                                                   not null,
  content    varchar(1850)                                                  not null,
  owner_id   bigint                                                         not null,
  count      integer                     default 0                          not null,
  created_at timestamp without time zone default (now() at time zone 'utc') not null
);

create unique index if not exists memes_guild_id_name_uindex
  on memes (guild_id, name);

create index if not exists memes_name_trgm_idx
  on memes using gin (name gin_trgm_ops);


create table if not exists prefixes
(
  guild_id bigint      not null
    constraint prefixes_pk
      primary key,
  prefix   varchar(32) not null
);

create unique index if not exists prefixes_guild_id_prefix_uindex
  on prefixes (guild_id asc, prefix desc);